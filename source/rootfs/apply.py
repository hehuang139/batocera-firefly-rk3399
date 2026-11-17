#!/usr/bin/env python3
"""Apply the small Firefly userspace delta to an extracted Batocera 40 rootfs."""
import argparse
import hashlib
import json
import stat
from pathlib import Path

SOURCE = Path(__file__).resolve().parent
GUARD = '''# Firefly board port: an upstream RockPro64 update removes its DTB/boot configuration.
FIREFLY_MODEL=$(tr -d '\\000' < /sys/firmware/devicetree/base/model 2>/dev/null || true)
FIREFLY_BOARD=$(cat /boot/boot/batocera.board 2>/dev/null || true)
if [ "$FIREFLY_MODEL" = "Firefly-RK3399 Board" ] || [ "$FIREFLY_BOARD" = firefly-rk3399 ]; then
    echo "Firefly RK3399 uses a board-specific image. Install a matching Firefly release image; the generic online updater is disabled." >&2
    exit 1
fi

'''


def sha(data):
    return hashlib.sha256(data).hexdigest()


def safe_target(root, relative):
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Invalid rootfs-relative target: {relative}")
    target = (root / path).resolve()
    if not target.is_relative_to(root):
        raise ValueError(f"Target escapes rootfs through a symlink: {relative}")
    return target


def plan(root):
    root = root.resolve()
    provenance = json.loads((SOURCE / "provenance.json").read_text())
    changes = {}
    for item in provenance["files"]:
        relative = item["target"]
        original = (SOURCE / "upstream" / relative).read_bytes()
        if sha(original) != item["sha256"]:
            raise ValueError(f"Bundled upstream source checksum mismatch: {relative}")
        overlay = SOURCE / "overlay" / relative
        if overlay.is_file():
            modified = overlay.read_bytes()
        elif relative == "usr/bin/batocera-upgrade":
            shebang = b"#!/bin/bash\n"
            if not original.startswith(shebang):
                raise ValueError("Unexpected upgrade script shebang")
            # Reject before installing the upstream EXIT cleanup trap: it removes
            # manually downloaded upgrade archives even when no upgrade occurred.
            modified = shebang + b"\n" + GUARD.encode() + original[len(shebang):]
        elif relative == "usr/share/batocera/datainit/system/batocera.conf":
            marker = b"\nupdates.enabled=1\n"
            if original.count(marker) != 1:
                raise ValueError("Default update setting is not unique")
            modified = original.replace(marker, b"\nupdates.enabled=0\n")
        elif relative == "etc/init.d/S32bluetooth":
            marker = b'        bluetoothstack="rfkreset bcm150"\n'
            if original.count(marker) != 1:
                raise ValueError("Bluetooth stack marker is not unique")
            replacement = marker + b'''        # Firefly's DT describes Broadcom UART serdev and its power/wake GPIOs.
        # The kernel owns this UART; do not also run hciattach or reset rfkill0.
        FIREFLY_MODEL=$(tr -d '\\000' < /sys/firmware/devicetree/base/model 2>/dev/null || true)
        if [ "$BOARD" = firefly-rk3399 ] || [ "$FIREFLY_MODEL" = "Firefly-RK3399 Board" ]; then
            bluetoothstack=""
        fi
'''
            modified = original.replace(marker, replacement)
        else:
            raise ValueError(f"No adaptation rule: {relative}")
        target = safe_target(root, relative)
        actual = target.read_bytes()
        if actual not in (original, modified):
            raise ValueError(f"Unexpected base file {relative}: sha256={sha(actual)}")
        changes[relative] = (modified, stat.S_IMODE(target.stat().st_mode))

    for item in sorted((SOURCE / "overlay").rglob("*")):
        if not item.is_file():
            continue
        relative = item.relative_to(SOURCE / "overlay").as_posix()
        if relative in changes:
            continue
        target = safe_target(root, relative)
        modified = item.read_bytes()
        if target.exists() and target.read_bytes() != modified:
            raise ValueError(f"Refusing to replace unknown file: {relative}")
        changes[relative] = (modified, stat.S_IMODE(item.stat().st_mode))
    return changes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rootfs", type=Path)
    parser.add_argument("--check", action="store_true", help="Check compatibility without changing files")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    root = args.rootfs.resolve()
    if root == Path("/") or not safe_target(root, "usr/share/batocera").is_dir():
        raise ValueError("Expected an extracted Batocera rootfs directory")
    changes = plan(root)
    report = {"rootfs": str(root), "check_only": args.check, "files": []}
    for relative, (data, mode) in changes.items():
        target = safe_target(root, relative)
        before = sha(target.read_bytes()) if target.exists() else None
        if not args.check:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            target.chmod(mode)
        report["files"].append({"path": relative, "before_sha256": before,
                                "after_sha256": sha(data), "mode": oct(mode)})
    report["status"] = "compatible" if args.check else "applied"
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
