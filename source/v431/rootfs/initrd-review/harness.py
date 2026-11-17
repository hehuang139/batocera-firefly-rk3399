from pathlib import Path
import json, subprocess
base=Path('/review')
source=(base/'init').read_text()
body=source[:source.index('\nif ! do_root\n')]
body=body.replace('read -r cmdline < /proc/cmdline', 'read -r cmdline < /review/cmdline.fixture')
assert body.count('exec switch_root')==1
body=body.replace('exec switch_root', 'switch_root')
results=[]
for device in ['/dev/mmcblk2p1','/dev/mmcblk1p1']:
 for secondary in [True,False]:
  records=base/'calls.log';records.write_text('')
  (base/'cmdline.fixture').write_text('dev='+device+' rootwait console=tty3 console=ttyS2,1500000n8\n')
  pre='''#!/bin/ash
mount() { printf 'mount %s\\n' "$*" >> /review/calls.log; return 0; }
mkdir() { return 0; }
switch_root() { printf 'switch_root %s\\n' "$*" >> /review/calls.log; return 0; }
seq() { echo 1; }
sleep() { return 0; }
test() {
'''+('''    if [ "$1" = -e ] && [ "$2" = /boot_root/boot/rufomaculata ]; then return 0; fi
''' if secondary else '')+'''    return 1
}
'''
  (base/'fixture.ash').write_text(pre+body+'\ndo_root\n')
  result=subprocess.run(['qemu-aarch64-static','-cpu','cortex-a72',str(base/'bin/busybox'),'ash',str(base/'fixture.ash')],capture_output=True,text=True)
  assert result.returncode==0,result.stderr
  calls=records.read_text().splitlines()
  assert 'mount -o ro '+device+' /boot_root' in calls,calls
  overlay=[c for c in calls if c.startswith('mount -t overlay')]
  expected='lowerdir=/overlay_root/base'+(':/overlay_root/base2' if secondary else '')+',upperdir=/overlay_root/overlay,workdir=/overlay_root/work'
  assert len(overlay)==1 and expected in overlay[0],overlay
  assert calls.index('mount /boot_root/boot/batocera /overlay_root/base') < calls.index(overlay[0]),calls
  if secondary:assert calls.index('mount /boot_root/boot/rufomaculata /overlay_root/base2') < calls.index(overlay[0]),calls
  assert calls[-1]=='switch_root /new_root /sbin/init',calls
  results.append({'device':device,'secondary':secondary,'result':'PASS','calls':calls})
(base/'harness-result.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results,indent=2))
