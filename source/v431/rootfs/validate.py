#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exercise Firefly 43.1 controls, startup delta, update refusal and file pins."""
import argparse
import sys
sys.dont_write_bytecode = True
import copy
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent

def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader))
    loader.exec_module(module)
    return module

apply = load('firefly_apply', HERE / 'apply.py')
hotkey = load('firefly_hotkey', HERE / 'overlay/usr/bin/firefly-select-hotkey')


def run_checks(root, bsp):
    manifest = json.loads((HERE / 'provenance.json').read_text())
    results = []
    def record(name, detail=None):
        results.append({'name': name, 'result': 'PASS', 'detail': detail})
    def check(value, message):
        if not value:
            raise AssertionError(message)
    def rejects(call, kind):
        try:
            call()
        except kind:
            return
        raise AssertionError('Expected input rejection')

    original = (HERE / 'upstream/usr/share/emulationstation/es_input.cfg').read_bytes()
    shared_path = 'usr/share/emulationstation/es_input.cfg'
    before = next(i['before'] for i in manifest['files'] if i['path'] == shared_path)
    check(apply.digest(HERE / 'upstream' / shared_path) == before['sha256'], 'Original controller DB pin')
    normalized, changed = hotkey.transform(original)
    check(normalized == (HERE / 'overlay' / shared_path).read_bytes(), 'Normalized full database')
    old, new = ET.fromstring(original), ET.fromstring(normalized)
    old_nodes, new_nodes = old.findall('inputConfig'), new.findall('inputConfig')
    check(len(old_nodes) == len(new_nodes), 'All controller entries retained')
    eligible = 0
    for first, second in zip(old_nodes, new_nodes):
        check(first.attrib == second.attrib, 'Controller identity retained')
        a, b = copy.deepcopy(first), copy.deepcopy(second)
        selects = first.findall("input[@name='select']")
        valid = (first.get('type') == 'joystick' and len(selects) == 1
                 and selects[0].get('type') == 'button'
                 and selects[0].get('id', '').isdigit() and selects[0].get('value') == '1')
        if valid:
            eligible += 1
            keys = second.findall("input[@name='hotkey']")
            check(len(keys) == 1 and keys[0].attrib == dict(selects[0].attrib, name='hotkey'), 'Select uses per-controller button ID')
            for node in list(a.findall("input[@name='hotkey']")): a.remove(node)
            for node in list(b.findall("input[@name='hotkey']")): b.remove(node)
        # Formatting whitespace is not a semantic controller mapping.
        check([(n.tag, n.attrib, (n.text or '').strip()) for n in a] == [(n.tag, n.attrib, (n.text or '').strip()) for n in b], 'Non-hotkey controller mappings preserved')
    check(hotkey.transform(normalized) == (normalized, 0), 'Normalization idempotence')
    record('complete_43_1_controller_database', {'controllers': len(old_nodes), 'eligible_select_buttons': eligible, 'changed_entries_and_hook': changed})

    fixture = b'''<inputList>
<inputConfig type="keyboard"><input name="select" type="key" id="42" value="1"/><input name="hotkey" type="key" id="43" value="1"/></inputConfig>
<inputConfig type="joystick" deviceName="no-select"><input name="hotkey" type="button" id="8" value="1"/></inputConfig>
<inputConfig type="joystick" deviceName="axis-select"><input name="select" type="axis" id="0" value="1"/><input name="hotkey" type="button" id="6" value="1"/></inputConfig>
<inputConfig type="joystick" deviceName="pad-a"><input name="select" type="button" id="6" value="1"/><input name="hotkey" type="button" id="8" value="1"/><input name="hotkey" type="button" id="9" value="1"/></inputConfig>
<inputConfig type="joystick" deviceName="pad-b"><input name="select" type="button" id="10" value="1"/></inputConfig>
<inputAction type="onfinish"><command>first-existing-command</command><command>/usr/bin/firefly-select-hotkey</command><command>last-existing-command</command><command>/usr/bin/firefly-select-hotkey</command></inputAction>
</inputList>'''
    transformed, _ = hotkey.transform(fixture)
    tree = ET.fromstring(transformed)
    check([c.text for c in tree.find("inputAction[@type='onfinish']").findall('command')] == ['first-existing-command', 'last-existing-command', hotkey.COMMAND], 'Existing onfinish command order')
    check(tree.find("inputConfig[@deviceName='pad-a']/input[@name='hotkey']").get('id') == '6', 'Pad A button')
    check(tree.find("inputConfig[@deviceName='pad-b']/input[@name='hotkey']").get('id') == '10', 'Pad B button')
    for name in ['no-select', 'axis-select']:
        check([n.attrib for n in tree.find("inputConfig[@deviceName='%s']" % name)] == [n.attrib for n in ET.fromstring(fixture).find("inputConfig[@deviceName='%s']" % name)], 'Unsupported Select preserved')
    check(tree.find("inputConfig[@type='keyboard']/input[@name='hotkey']").get('id') == '43', 'Keyboard preserved')
    record('varied_ids_keyboard_invalid_select_and_hook_order')

    with tempfile.TemporaryDirectory(prefix='firefly431-hotkey-') as directory:
        config_dir = Path(directory) / 'emulationstation'
        user = config_dir / 'es_input.cfg'
        check(hotkey.initialize_user_file(user), 'First-boot initialization')
        check(user.stat().st_mode & 0o777 == 0o644, 'First-user mode')
        initial = user.read_bytes()
        check(ET.fromstring(initial).find('inputAction/command').text == hotkey.COMMAND, 'First-user onfinish installed')
        check(not hotkey.initialize_user_file(user) and user.read_bytes() == initial, 'Existing user config never overwritten')
        check(not list(config_dir.glob('*.pre-select-hotkey')), 'No backup of empty first-user config')
        # Model ES 43.1 writeDeviceConfig(): persist user and last controller,
        # execute the installed command synchronously, then reload user XML.
        doc = ET.fromstring(initial)
        controller = ET.SubElement(doc, 'inputConfig', {'type': 'joystick', 'deviceName': 'new-pair'})
        ET.SubElement(controller, 'input', {'name': 'select', 'type': 'button', 'id': '11', 'value': '1'})
        ET.SubElement(controller, 'input', {'name': 'start', 'type': 'button', 'id': '12', 'value': '1'})
        user.write_bytes(ET.tostring(doc))
        first_mapping = user.read_bytes()
        last = config_dir / 'es_last_input.cfg'
        lastroot = ET.Element('inputList');lastroot.append(copy.deepcopy(controller));last.write_bytes(ET.tostring(lastroot))
        subprocess.run(['python3', str(HERE / 'overlay/usr/bin/firefly-select-hotkey'), '--config-dir', str(config_dir)], check=True, capture_output=True)
        check(ET.parse(user).find("inputConfig/input[@name='hotkey']").get('id') == '11', 'New pair reload uses Select')
        check(ET.parse(last).find("inputConfig/input[@name='hotkey']").get('id') == '11', 'Last controller sharing config normalized')
        check(ET.parse(last).find('inputAction') is None, 'Last config does not install hook')
        check(user.with_name('es_input.cfg.pre-select-hotkey').read_bytes() == first_mapping, 'Original user backup preserved')
        subprocess.run(['python3', str(HERE / 'overlay/usr/bin/firefly-select-hotkey'), '--config-dir', str(config_dir)], check=True, capture_output=True)
        check(user.with_name('es_input.cfg.pre-select-hotkey').read_bytes() == first_mapping, 'Backup stable on repeated run')
        bad = config_dir / 'malformed.cfg';bad.write_bytes(b'<inputList><broken>')
        rejects(lambda: hotkey.update_file(bad), ET.ParseError)
        check(bad.read_bytes() == b'<inputList><broken>', 'Malformed config left intact')
        link = config_dir / 'symlink.cfg';link.symlink_to(user)
        rejects(lambda: hotkey.update_file(link), OSError)
        concurrent = config_dir / 'concurrent.cfg';concurrent.write_bytes(fixture)
        transform = hotkey.transform
        def racing_transform(*args, **kwargs):
            value = transform(*args, **kwargs)
            concurrent.write_bytes(b'<inputList><!-- competing ES write --></inputList>')
            return value
        hotkey.transform = racing_transform
        try:
            rejects(lambda: hotkey.update_file(concurrent), RuntimeError)
        finally:
            hotkey.transform = transform
        check(b'competing ES write' in concurrent.read_bytes(), 'Concurrent write not overwritten')
        check(not list(config_dir.glob('.select-hotkey-*')), 'Temporary files cleaned')
    record('first_boot_new_pair_save_reload_backup_malformed_symlink_concurrency')

    with tempfile.TemporaryDirectory(prefix='firefly431-fan-') as directory:
        base = Path(directory)
        for number, name in [(0, 'cpu_thermal'), (4, 'pwmfan'), (7, 'gpu_thermal')]:
            hwmon = base / ('hwmon%d' % number);hwmon.mkdir();(hwmon / 'name').write_text(name + '\n');(hwmon / 'pwm1').write_text('17\n')
        script = (HERE / 'overlay/etc/init.d/S02fan').read_text().replace('/sys/class/hwmon', str(base))
        subprocess.run(['/bin/sh', '-c', script, 'S02fan', 'start'], check=True)
        check((base / 'hwmon4/pwm1').read_text() == '100\n', 'Pwm fan device updated')
        check((base / 'hwmon0/pwm1').read_text() == '17\n' and (base / 'hwmon7/pwm1').read_text() == '17\n', 'Thermal sensors untouched')
    record('fan_discovery_ignores_hwmon_number')

    with tempfile.TemporaryDirectory(prefix='firefly431-updater-') as directory:
        base = Path(directory)
        model = base / 'sys/firmware/devicetree/base/model';model.parent.mkdir(parents=True);model.write_bytes(b'Firefly-RK3399 Board\x00')
        board = base / 'boot/boot/batocera.board';board.parent.mkdir(parents=True);board.write_text('firefly-rk3399\n')
        upgrade = base / 'userdata/system/upgrade';upgrade.mkdir(parents=True)
        for name in ['boot.tar.xz', 'boot.tar.xz.md5', 'upgrade_message.txt']:(upgrade / name).write_bytes(b'preserve-upgrade-archive')
        script = (HERE / 'overlay/usr/bin/batocera-upgrade').read_text()
        check(script.index('FIREFLY_MODEL=') < script.index('trap do_clean EXIT'), 'Guard precedes archive deletion trap')
        for name in ['/sys/', '/boot/', '/userdata/']:script = script.replace(name, str(base) + name)
        result = subprocess.run(['/bin/bash', '-c', script], capture_output=True, text=True)
        check(result.returncode == 1 and 'matching Firefly release image' in result.stderr, 'Generic upgrade refused')
        check(all(p.read_bytes() == b'preserve-upgrade-archive' for p in upgrade.iterdir()), 'Manual archives preserved')
    record('generic_upgrade_refused_before_cleanup')

    apply.plan(root, bsp)
    for item in manifest['files']:
        check(apply.identity(apply.target(root, item['path'])) == item['after'], 'Final file differs: ' + item['path'])
    check(apply.inventory(root, 'lib/modules') == manifest['bsp_modules'], 'Exact complete BSP modules')
    check(sorted(p.name for p in (root / 'lib/modules').iterdir()) == ['6.6.27'], 'Only matching kernel version')
    check(not (root / 'etc/init.d/S02overclock').exists(), 'N2 overclock removed')
    check(b'ttyS2 1500000 vt100 # GENERIC_SERIAL' in (root / 'etc/inittab').read_bytes(), 'Firefly serial UART and speed')
    check(not any((HERE / 'overlay').rglob('*.pyc')), 'No generated bytecode in overlay')
    check(not (root / 'usr/bin/__pycache__/firefly-select-hotkeycpython-310.pyc').exists(), 'No host-generated normalizer bytecode')
    check((root / 'usr/share/batocera/batocera.arch').read_bytes() == b'rk3399', 'Exact RK3399 arch')
    check('bluetoothstack=""' in (root / 'etc/init.d/S32bluetooth').read_text(), 'Bluetooth kernel serdev retained')
    check(b'updates.enabled=0\n' in (root / 'usr/share/batocera/datainit/system/batocera.conf').read_bytes(), 'Online update checks disabled')
    for relative in ['etc/init.d/S02fan', 'etc/init.d/S30selecthotkey', 'usr/bin/batocera-upgrade']:
        subprocess.run(['/bin/sh' if not relative.endswith('batocera-upgrade') else '/bin/bash', '-n', str(root / relative)], check=True)
    record('applied_files_invariants_modules_arch_shell_syntax', {'files': len(manifest['files']), 'module_files': sum(i['type'] == 'file' for i in manifest['bsp_modules']), 'version': manifest['version_text'].strip()})
    # Do not mutate the real image for rejection tests.
    with tempfile.TemporaryDirectory(prefix='firefly431-reject-') as directory:
        fake = Path(directory) / 'root';(fake / 'usr/share/batocera').mkdir(parents=True)
        (fake / 'usr/share/batocera/batocera.version').write_text('40 2024/08/01\n')
        rejects(lambda: apply.plan(fake, bsp), ValueError)
        rejects(lambda: apply.target(fake, '../escape'), ValueError)
        (fake / 'outside').symlink_to('/tmp')
        rejects(lambda: apply.target(fake, 'outside/escape'), ValueError)
        fakebsp = Path(directory) / 'bsp'; (fakebsp / 'lib/modules').mkdir(parents=True)
        rejects(lambda: apply.plan(root, fakebsp), ValueError)
    record('wrong_release_bsp_and_escaping_paths_rejected')
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rootfs', type=Path, required=True)
    parser.add_argument('--bsp-rootfs', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    results = run_checks(args.rootfs.resolve(), args.bsp_rootfs.resolve())
    report = {'result': 'PASS', 'checks': results}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
