#!/usr/bin/env python3
"""Exercise Select mapping with saved XML and the actual Batocera 40 generators."""
import hashlib
import importlib.machinery
import importlib.util
import json
import logging
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import xml.etree.ElementTree as ET

sys.dont_write_bytecode = True
BASE = Path(__file__).resolve().parent
PROGRAM = BASE / "overlay/usr/bin/firefly-select-hotkey"
CONFIG = BASE / "overlay/usr/share/batocera/datainit/system/configs/emulationstation/es_input.cfg"
checks = []


def check(name, condition):
    checks.append({"name": name, "passed": bool(condition)})
    if not condition:
        raise AssertionError(name)


def inputs(controller):
    return {i.get("name"): dict(i.attrib) for i in controller.findall("input")}


def signatures(root):
    return [(dict(c.attrib), [dict(i.attrib) for i in c.findall("input")
                             if i.get("name") != "hotkey"])
            for c in root.findall("inputConfig")]


def call(directory):
    return subprocess.run([str(PROGRAM), "--config-dir", str(directory)],
                          capture_output=True, text=True)


def load_module(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader))
    sys.modules[name] = module
    loader.exec_module(module)
    return module


def pad(parent, name, select_id=None, hotkey_id="15", kind="joystick"):
    controller = ET.SubElement(parent, "inputConfig", {
        "type": kind, "deviceName": name, "deviceGUID": name.replace(" ", "-")})
    for button, ident in [("start", "7"), ("a", "1"), ("b", "0"), ("x", "3"), ("y", "2")]:
        ET.SubElement(controller, "input", {
            "name": button, "type": "button", "id": ident, "value": "1", "code": str(300 + int(ident))})
    if select_id is not None:
        ET.SubElement(controller, "input", {
            "name": "select", "type": "key" if kind == "keyboard" else "button",
            "id": str(select_id), "value": "1", "code": str(314 + int(select_id))})
    if hotkey_id is not None:
        ET.SubElement(controller, "input", {
            "name": "hotkey", "type": "button", "id": hotkey_id, "value": "1", "code": "316"})
    return controller


def main():
    manifest = json.loads((BASE / "manifest.json").read_text())
    actual_files = {p.relative_to(BASE / "overlay").as_posix()
                    for p in (BASE / "overlay").rglob("*") if p.is_file()}
    check("overlay contains exactly the three declared files",
          actual_files == {f["path"] for f in manifest["files"]})
    check("manifest file hashes and modes match", all(
        hashlib.sha256((BASE / "overlay" / f["path"]).read_bytes()).hexdigest() == f["sha256"]
        and format((BASE / "overlay" / f["path"]).stat().st_mode & 0o777, "04o") == f["mode"]
        for f in manifest["files"]))
    old = ET.parse(BASE / "provenance/es_input.cfg").getroot()
    new = ET.parse(CONFIG).getroot()
    check("261 default profiles retain identity and every non-hotkey input", signatures(old) == signatures(new))
    eligible = [c for c in new.findall("inputConfig")
                if c.get("type") == "joystick" and "select" in inputs(c)]
    check("257 default joystick profiles use their own Select mapping", len(eligible) == 257 and all(
        inputs(c)["hotkey"] == dict(inputs(c)["select"], name="hotkey") for c in eligible))
    preserved = [(a, b) for a, b in zip(old.findall("inputConfig"), new.findall("inputConfig"))
                 if a.get("type") != "joystick" or "select" not in inputs(a)]
    check("keyboard and all three profiles without Select retain hotkeys", len(preserved) == 4 and all(
        inputs(a) == inputs(b) for a, b in preserved))
    check("default onfinish has one executable normalizer command",
          [c.text for c in new.findall("inputAction[@type='onfinish']/command")] == ["/usr/bin/firefly-select-hotkey"])

    with tempfile.TemporaryDirectory(prefix="select-hotkey-test-") as temporary:
        directory = Path(temporary)
        path = directory / "es_input.cfg"
        root = ET.Element("inputList")
        for index in [0, 6, 10, 14]:
            pad(root, f"手柄 {index}", index)
        pad(root, "No Select")
        pad(root, "Keyboard", 8, kind="keyboard")
        action = ET.SubElement(root, "inputAction", {"type": "onfinish", "extra": "preserve"})
        ET.SubElement(action, "command").text = "echo 'existing hook'"
        ET.SubElement(action, "command").text = "echo 'second hook'"
        ET.SubElement(root, "inputAction", {"type": "custom"}).text = "unrelated action"
        original = ET.tostring(root)
        path.write_bytes(original)
        path.chmod(0o640)
        result = call(directory)
        check("migration executes successfully as an executable Python script", result.returncode == 0)
        mapped = ET.parse(path).getroot()
        check("different controller IDs 0, 6, 10 and 14 map independently", all(
            inputs(c)["hotkey"]["id"] == str(index)
            and inputs(c)["hotkey"]["code"] == str(314 + index)
            for index, c in zip([0, 6, 10, 14], mapped.findall("inputConfig")[:4])))
        check("existing onfinish commands stay ordered and normalizer runs last",
              [c.text for c in mapped.findall("inputAction[@type='onfinish']/command")] ==
              ["echo 'existing hook'", "echo 'second hook'", "/usr/bin/firefly-select-hotkey"])
        check("other inputAction data survives migration", mapped.find("inputAction[@type='custom']").text == "unrelated action")
        check("original XML backup is exact", path.with_name(path.name + ".pre-select-hotkey").read_bytes() == original)
        check("existing file mode is preserved", path.stat().st_mode & 0o777 == 0o640)
        before = path.read_bytes(), path.stat().st_mtime_ns
        check("second invocation is a no-op", call(directory).returncode == 0 and
              before == (path.read_bytes(), path.stat().st_mtime_ns))

        # Emulate ES save: preserve root/actions, replace this controller entry,
        # write es_last_input.cfg, then execute the synchronous onfinish hook.
        first = mapped.findall("inputConfig")[0]
        mapped.remove(first)
        paired = pad(mapped, "New Bluetooth Controller", 12, "16")
        last_root = ET.Element("inputList")
        last_root.append(ET.fromstring(ET.tostring(paired)))
        last = directory / "es_last_input.cfg"
        last.write_bytes(ET.tostring(last_root))
        path.write_bytes(ET.tostring(mapped))
        check("newly paired controller save/onfinish succeeds", call(directory).returncode == 0)
        reloaded = ET.parse(path).getroot()
        pair = reloaded.find("inputConfig[@deviceName='New Bluetooth Controller']")
        check("ES reload sees new controller's Select id 12 and code 326",
              inputs(pair)["hotkey"] == dict(inputs(pair)["select"], name="hotkey"))
        check("es_last_input sharing record uses the same hotkey without adding hooks",
              inputs(ET.parse(last).getroot().find("inputConfig"))["hotkey"]["id"] == "12"
              and not ET.parse(last).getroot().findall("inputAction"))
        check("backup remains the pre-migration file after new pairing",
              path.with_name(path.name + ".pre-select-hotkey").read_bytes() == original)

        # Import unchanged Batocera 40 modules. Stub only hardware discovery and
        # logger/settings imports; use the real XML, SDL and RetroArch functions.
        for name in ["pyudev", "evdev", "batoceraFiles", "utils", "utils.logger", "settings", "settings.unixSettings"]:
            sys.modules[name] = types.ModuleType(name)
        sys.modules["utils.logger"].get_logger = logging.getLogger
        sys.modules["settings.unixSettings"].UnixSettings = object
        sys.modules["batoceraFiles"].esInputs = str(path)
        controllers = load_module("controllersConfig", BASE / "provenance/controllersConfig.py")
        retro = load_module("libretroControllers", BASE / "provenance/libretroControllers.py")
        loaded = controllers.loadAllControllersConfig()
        byname = controllers.loadAllControllersByNameConfig()
        check("both real configgen loaders receive Select as hotkey", all(
            byname[name].inputs["hotkey"].id == str(index)
            for name, index in [("手柄 6", 6), ("手柄 10", 10), ("手柄 14", 14), ("New Bluetooth Controller", 12)]))
        newpad = byname["New Bluetooth Controller"]
        newpad.player = "1"
        newpad.realName = "New Bluetooth Controller"
        class Settings:
            def __init__(self): self.values = {}
            def save(self, key, value): self.values[key] = value
        settings = Settings()
        retro.writeHotKeyConfig(settings, {"1": newpad})
        check("real RetroArch generator emits Select hotkey ID 12", settings.values == {"input_enable_hotkey_btn": "12"})
        system = types.SimpleNamespace(name="snes", config={"core": "snes9x"})
        buttons = retro.generateControllerConfig(newpad, {
            "start": "exit_emulator", "b": "menu_toggle", "y": "save_state", "x": "load_state"}, system, False)
        check("RetroArch keeps Start exit, B menu, Y save and X load combinations",
              all(buttons[key] == value for key, value in {
                  "input_exit_emulator_btn": "7", "input_menu_toggle_btn": "0",
                  "input_save_state_btn": "2", "input_load_state_btn": "3"}.items()))
        sdl = newpad.generateSDLGameDBLine()
        check("SDL retains Back/Select and suppresses duplicate Guide mapping", "back:b12," in sdl and "guide:" not in sdl)

        malformed = b"<inputList><broken>"
        path.write_bytes(malformed)
        check("malformed XML is reported without replacement", call(directory).returncode != 0 and path.read_bytes() == malformed)
        path.unlink()
        target = directory / "target.xml"
        target.write_bytes(original)
        path.symlink_to(target)
        check("symlink config is refused and target preserved", call(directory).returncode != 0 and target.read_bytes() == original)
        path.unlink()
        check("missing input file is tolerated", call(directory).returncode == 0 and not path.exists())

    manager = (BASE / "provenance/InputManager.cpp").read_text()
    save = manager[manager.index("void InputManager::writeDeviceConfig"):manager.index("void InputManager::doOnFinish")]
    platform = (BASE / "provenance/Platform.cpp").read_text()
    constructor = platform[platform.index("ProcessStartInfo::ProcessStartInfo(const std::string& cmd)"):platform.index("int ProcessStartInfo::run()")]
    check("pinned ES source executes onfinish synchronously then reloads input",
          save.index("doOnFinish();") < save.index("loadInputConfig(config);") and "waitForExit = true;" in constructor)
    check("startup ordering copies userdata before normalizing and launching ES",
          "system/configs/emulationstation/es_input.cfg" in (BASE / "provenance/S12populateshare").read_text()
          and "for i in /etc/init.d/S??*" in (BASE / "provenance/rcS").read_text()
          and "S12populateshare" < "S30selecthotkey" < "S31emulationstation")
    subprocess.run(["sh", "-n", str(BASE / "overlay/etc/init.d/S30selecthotkey")], check=True)
    check("startup shell syntax passes", True)
    before_manifest = (BASE / "manifest.json").read_bytes()
    subprocess.run([sys.executable, str(BASE / "build-config.py"), "--config-source",
                    str(BASE / "provenance/es_input.cfg")], check=True, capture_output=True)
    check("standalone source regeneration reproduces the exact manifest",
          (BASE / "manifest.json").read_bytes() == before_manifest)
    with tempfile.NamedTemporaryFile() as wrong:
        wrong.write(b"<inputList/>")
        wrong.flush()
        result = subprocess.run([sys.executable, str(BASE / "build-config.py"),
                                 "--config-source", wrong.name], capture_output=True, text=True)
        check("source generator rejects wrong input hash before changing output",
              result.returncode != 0 and "SHA256 mismatch" in result.stderr
              and (BASE / "manifest.json").read_bytes() == before_manifest)
    report = {"status": "PASS", "passed": len(checks), "checks": checks,
              "environment": {"python": sys.version.split()[0], "host": "Linux host; temporary XML configurations",
                  "runtime_generators": "Unmodified Batocera 40 controllersConfig.py and libretroControllers.py extracted from the actual image",
                  "hardware_imports": "pyudev/evdev imports stubbed; no device-discovery functions called",
                  "es_save_flow": "save/onfinish/reload XML fixture; source order verified at pinned ES commit"}}
    (BASE / "validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "passed": report["passed"]}))


if __name__ == "__main__":
    main()
