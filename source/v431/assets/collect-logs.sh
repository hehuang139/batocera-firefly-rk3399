#!/bin/sh
# SPDX-License-Identifier: MIT
# Run over SSH: sh /boot/collect-logs.sh
set -u
OUT="/userdata/system/logs/firefly-rk3399-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUT"
{ uname -a; cat /usr/share/batocera/batocera.version; cat /boot/boot/batocera.board; cat /proc/cmdline; tr '\0' '\n' < /proc/device-tree/model; } > "$OUT/system.txt" 2>&1
dmesg > "$OUT/dmesg.txt" 2>&1
{ free -m; cat /proc/swaps; cat /proc/mounts; lsblk -o NAME,SIZE,FSTYPE,LABEL,MOUNTPOINT; } > "$OUT/storage-memory.txt" 2>&1
{ ip address; ip route; rfkill list; lsusb; lsmod; } > "$OUT/devices.txt" 2>&1
{ aplay -l; pactl info; pactl list short cards; pactl list short sinks; } > "$OUT/audio.txt" 2>&1
{ for p in /sys/class/drm/card*-*/status; do printf '\n%s\n' "$p"; cat "$p"; done; ls -l /dev/dri; } > "$OUT/display.txt" 2>&1
{ for p in /sys/class/thermal/thermal_zone*/temp; do printf '\n%s\n' "$p"; cat "$p"; done; } > "$OUT/temperature.txt" 2>&1
cp /userdata/system/logs/es_launch_stdout.log /userdata/system/logs/es_launch_stderr.log "$OUT/" 2>/dev/null || true
printf 'Logs: %s\n' "$OUT"
