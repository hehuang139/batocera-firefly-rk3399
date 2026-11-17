#!/usr/bin/env python3
"""Generate the Select-hotkey default database from the pinned Batocera image."""
import argparse
import hashlib
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

sys.dont_write_bytecode = True

BASE = Path(__file__).resolve().parent
CONFIG = "usr/share/batocera/datainit/system/configs/emulationstation/es_input.cfg"
PROGRAM = "usr/bin/firefly-select-hotkey"
INIT = "etc/init.d/S30selecthotkey"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--squashfs", type=Path)
    source.add_argument("--config-source", type=Path)
    args = parser.parse_args()
    original = (args.config_source.read_bytes() if args.config_source else
                subprocess.check_output(["unsquashfs", "-cat", str(args.squashfs), CONFIG]))
    pinned = json.loads((BASE / "inputs.json").read_text())
    if sha(original) != pinned["default_config_sha256"]:
        raise SystemExit("original es_input.cfg SHA256 mismatch")
    loader = importlib.machinery.SourceFileLoader("select_hotkey", str(BASE / "overlay" / PROGRAM))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    output, changed = module.transform(original)
    destination = BASE / "overlay" / CONFIG
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(output)
    destination.chmod(0o644)
    (BASE / "overlay" / PROGRAM).chmod(0o755)
    (BASE / "overlay" / INIT).chmod(0o755)
    root = ET.fromstring(output)
    mapped = sum(c.get("type") == "joystick" and c.find("input[@name='select']") is not None
                 for c in root.findall("inputConfig"))
    manifest = {
        "format": 1,
        "base": "Batocera 40 RockPro64 20240801 / Firefly RK3399 test1",
        "policy": "Each joystick's configured Select button is its hotkey; keyboard and devices without Select retain their mappings.",
        "changed_controller_and_hook_entries": changed,
        "joystick_profiles_with_select": mapped,
        "default_config_upstream_sha256": sha(original),
        "files": [
            {"path": name, "sha256": sha((BASE / "overlay" / name).read_bytes()),
             "mode": format((BASE / "overlay" / name).stat().st_mode & 0o777, "04o"),
             "uid": 0, "gid": 0,
             "upstream_sha256": sha(original) if name == CONFIG else None}
            for name in [CONFIG, PROGRAM, INIT]
        ],
        "emulationstation_commit": "0261e73a172fcc6e01f73c9d5988f60bc0cb40fd",
        "hook": {"event": "inputAction type=onfinish", "synchronous": True,
                 "reload_after_command": True,
                 "startup_after": "S12populateshare", "startup_before": "S31emulationstation"},
    }
    (BASE / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"files": len(manifest["files"]), "mapped_profiles": mapped, "changed_entries": changed}))


if __name__ == "__main__":
    main()
