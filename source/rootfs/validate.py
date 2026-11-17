#!/usr/bin/env python3
"""Validate the userspace delta without running target executables or changing rootfs."""
import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rootfs", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("adapt", Path(__file__).with_name("apply.py"))
    adapt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapt)
    changes = adapt.plan(args.rootfs.resolve())
    checks = []

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append(name)

    with tempfile.TemporaryDirectory(prefix="firefly-rootfs-test-") as temp:
        test = Path(temp)
        for relative, (data, _) in changes.items():
            if data.startswith(b"#!/"):
                script = test / Path(relative).name
                script.write_bytes(data)
                result = subprocess.run(["bash", "-n", str(script)], capture_output=True)
                check(f"shell syntax: {relative}", result.returncode == 0)

        hwmon = test / "sys/class/hwmon"
        for name, device, value in [("hwmon0", "thermal", "19\n"),
                                    ("hwmon2", "pwmfan", "0\n")]:
            path = hwmon / name
            path.mkdir(parents=True)
            (path / "name").write_text(device + "\n")
            (path / "pwm1").write_text(value)
        fan = test / "fan.sh"
        fan.write_bytes(changes["etc/init.d/S02fan"][0].replace(b"/sys/", (temp + "/sys/").encode()))
        result = subprocess.run(["sh", str(fan), "start"], capture_output=True)
        check("fan script succeeds with reordered hwmon devices", result.returncode == 0)
        check("fan control targets pwmfan", (hwmon / "hwmon2/pwm1").read_text() == "100\n")
        check("fan control leaves unrelated hwmon untouched", (hwmon / "hwmon0/pwm1").read_text() == "19\n")
        (hwmon / "hwmon2/pwm1").unlink()
        result = subprocess.run(["sh", str(fan), "start"], capture_output=True)
        check("fan script tolerates a board without controllable fan", result.returncode == 0)

        model = test / "sys/firmware/devicetree/base/model"
        model.parent.mkdir(parents=True)
        model.write_bytes(b"Firefly-RK3399 Board\0")
        board = test / "boot/boot/batocera.board"
        board.parent.mkdir(parents=True)
        board.write_text("firefly-rk3399\n")
        marker = test / "wrong-hdmi-loop-started"
        stub = test / "batocera-check-hdmi"
        stub.write_text(f"#!/bin/sh\ntouch '{marker}'\n")
        stub.chmod(0o755)
        hdmi = test / "hdmi.sh"
        hdmi.write_bytes(changes["etc/init.d/S33checkhdmi"][0].replace(b"/sys/", (temp + "/sys/").encode()))
        result = subprocess.run(["sh", str(hdmi), "start"], capture_output=True,
                                env=dict(os.environ, PATH=temp + ":" + os.environ["PATH"]))
        check("Firefly does not launch RG552 GPIO watcher", result.returncode == 0 and not marker.exists())

        upgrade = test / "upgrade.sh"
        script = changes["usr/bin/batocera-upgrade"][0]
        for path in [b"/sys/", b"/boot/", b"/userdata/"]:
            script = script.replace(path, temp.encode() + path)
        upgrade.write_bytes(script)
        upgrade_dir = test / "userdata/system/upgrade"
        upgrade_dir.mkdir(parents=True)
        preserved_files = {"boot.tar.xz": b"user-provided manual upgrade archive\0\xff",
                           "boot.tar.xz.md5": b"user-provided checksum\n",
                           "upgrade_message.txt": b"existing status\n"}
        for name, data in preserved_files.items():
            (upgrade_dir / name).write_bytes(data)
        result = subprocess.run(["bash", str(upgrade)], capture_output=True)
        check("generic upgrade is blocked on Firefly", result.returncode == 1 and b"board-specific image" in result.stderr)
        check("rejected upgrade preserves manual archive and metadata",
              all((upgrade_dir / name).read_bytes() == data for name, data in preserved_files.items()))
        check("Firefly rejection precedes upstream EXIT trap",
              script.index(b"FIREFLY_MODEL=") < script.index(b"trap do_clean EXIT"))

        fixture = test / "rootfs"
        shutil.copytree(adapt.SOURCE / "upstream", fixture)
        leaf = fixture / "etc/init.d/S02fan"
        original_fan = leaf.read_bytes()
        outside = test / "outside-S02fan"
        outside.write_bytes(original_fan)
        leaf.unlink()
        leaf.symlink_to(outside)
        try:
            adapt.plan(fixture)
        except ValueError as error:
            check("target symlink outside rootfs is rejected", "escapes rootfs" in str(error))
        else:
            raise AssertionError("External target symlink was accepted")
        check("external file is preserved", outside.read_bytes() == original_fan)
        leaf.unlink()
        leaf.write_bytes(original_fan)

        outside_dir = test / "outside-etc"
        (fixture / "etc").rename(outside_dir)
        (fixture / "etc").symlink_to(outside_dir, target_is_directory=True)
        try:
            adapt.plan(fixture)
        except ValueError as error:
            check("parent directory symlink outside rootfs is rejected", "escapes rootfs" in str(error))
        else:
            raise AssertionError("External parent symlink was accepted")
        (fixture / "etc").unlink()
        outside_dir.rename(fixture / "etc")

        # A not-yet-created overlay leaf also needs its existing parents checked.
        sysconfigs = fixture / "usr/share/batocera/sysconfigs"
        external_sysconfigs = test / "external-sysconfigs"
        external_sysconfigs.mkdir()
        sysconfigs.symlink_to(external_sysconfigs, target_is_directory=True)
        try:
            adapt.plan(fixture)
        except ValueError as error:
            check("new overlay through external parent symlink is rejected", "escapes rootfs" in str(error))
        else:
            raise AssertionError("External overlay parent symlink was accepted")
        sysconfigs.unlink()

        internal_fan = fixture / "S02fan-internal"
        leaf.rename(internal_fan)
        leaf.symlink_to("../../S02fan-internal")
        check("symlinks wholly within rootfs remain supported", len(adapt.plan(fixture)) == 6)

    check("six scoped files adapted", len(changes) == 6)
    report = {"status": "PASS", "checks": checks, "count": len(checks),
              "rootfs": str(args.rootfs.resolve())}
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
