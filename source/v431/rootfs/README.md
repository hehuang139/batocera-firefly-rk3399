# Firefly RK3399 Batocera 43.1 rootfs adaptation

This directory contains a pinned delta for the official Batocera 43.1
Odroid N2+ ARM64 rootfs. `provenance.json` records the original and final file
identities, the complete donor and replacement kernel-module inventories,
and retained 43.1 executable/script identities. `research.json` records the
upstream release configs and EmulationStation source used for the port.

Run with the extracted 43.1 rootfs and the extracted Firefly RK3399 BSP tree:

```sh
python3 apply.py --rootfs /stage/rootfs --bsp-rootfs /stage/bsp-rootfs \
  --report /project/logs/v431/rootfs-check.json --check
python3 apply.py --rootfs /stage/rootfs --bsp-rootfs /stage/bsp-rootfs \
  --report /project/logs/v431/rootfs-adaptation.json
python3 validate.py --rootfs /stage/rootfs --bsp-rootfs /stage/bsp-rootfs \
  --report /project/logs/v431/rootfs-validation.json
```

The apply step needs root inside the builder to preserve root-owned image
files. It validates all pinned inputs before making changes. `prepare.py`
records the initial delta and refuses to replace the frozen provenance.
Image rebuilds use `apply.py` with the committed provenance and overlay.

## Board changes

- Preserve the exact `43.1 2026/06/01 19:14` version and 43.1 ES,
  RetroArch, Python, PipeWire, Panfrost Mesa and Labwc components.
- Set `batocera.arch` to `rk3399`; install the upstream 43.1 RK3399
  configgen defaults instead of S922X emulator defaults.
- Replace the entire 6.6.56 donor module tree with the 841 files from the
  Firefly BSP's matching 6.6.27 module tree. No donor modules remain.
- Use the BSP AP6356S Wi-Fi/Bluetooth firmware files listed in provenance.
- Remove the N2 overclock service. Discover the PWM fan by its `pwmfan`
  device name, so thermal sensor enumeration cannot redirect fan writes.
- Route automatic HDMI audio through the 43.1 RK3399 PipeWire logic.
  Retain the common 43.1 Bluetooth service with its empty vendor attach
  list; UART Bluetooth remains owned by the kernel serdev driver.
- Use Firefly UART `ttyS2` at 1500000 baud instead of the donor's `ttyAML0`.
- Disable online update checking and reject the generic updater before
  its EXIT cleanup handler, preserving manually downloaded archives.

## Select hotkey and first boot

The full 43.1 shared database contains 304 controller records. The
normalizer uses each joystick's own valid Select button ID as `hotkey`;
301 records qualify. Keyboard and unsupported Select mappings keep their
existing mappings. 178 controller/hook entries change in the database.

In 43.1, default controller mappings live in
`/usr/share/emulationstation/es_input.cfg`. The user input XML is initially
absent. `S30selecthotkey` atomically creates a small user input XML with the
normalizer's `onfinish` command before S31 starts ES. Shared controller
mappings remain in the shared database. On subsequent controller setup,
ES saves the user mapping and `es_last_input.cfg`, executes `onfinish`
synchronously, then reloads the normalized mapping. Existing commands
keep their order, with the Select normalizer last. The first user mapping
that is changed is backed up once; malformed files, symlinks and concurrent
writes are not overwritten.

`validate.py` exercises database preservation, varied controller button
IDs, first boot/new pair/save/reload behavior, backups, malformed XML,
symlink/concurrent-write protection, reordered fan devices, updater
archive preservation, exact final files/modules and wrong-release/path
rejection. Reports contain the checks actually executed.
