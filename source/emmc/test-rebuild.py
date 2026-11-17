#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Small-file checks for eMMC release validation and rebuild orchestration."""
import contextlib
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
checks=[]
spec=importlib.util.spec_from_file_location('release',HERE/'release-manifest.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def reject(name,call):
    try:call()
    except (OSError,ValueError):checks.append(name)
    else:raise AssertionError(name)


with tempfile.TemporaryDirectory(prefix='firefly-rebuild-test-') as d:
    root=Path(d)
    image=root/'firmware.img';raw=bytes(range(256))*128;image.write_bytes(raw)
    packed=Path(str(image)+'.gz')
    with gzip.open(packed,'wb') as f:f.write(raw)
    sidecar=image.with_suffix('.manifest.json')
    meta={'mode':'emmc','board':'firefly-rk3399','image':image.name,'bytes':len(raw),
          'root_device':'/dev/mmcblk2p1','sha256':hashlib.sha256(raw).hexdigest()}
    sidecar.write_text(json.dumps(meta));m.IMAGE_BYTES=len(raw)
    def release(output):
        with patch.object(sys,'argv',['release-manifest.py',str(image),str(output)]),contextlib.redirect_stdout(io.StringIO()):m.main()
    release(root/'manifest.json')
    assert json.loads((root/'manifest.json').read_text())['compressed']['sha256']==m.sha(packed)
    checks.append('matching raw gzip and metadata accepted')
    reject('existing output refused',lambda:release(root/'manifest.json'))
    outputlink=root/'outlink';outputlink.symlink_to(root/'manifest.json')
    reject('output symlink refused',lambda:release(outputlink))
    for field,value in [('mode','installer'),('board','rockpro64'),('root_device','/dev/mmcblk1p1'),
                        ('image','another.img'),('bytes',1),('sha256','0'*64)]:
        changed=dict(meta);changed[field]=value;sidecar.write_text(json.dumps(changed))
        reject('mismatched metadata '+field+' refused',lambda:release(root/'rejected.json'))
        assert not (root/'rejected.json').exists()
    sidecar.write_text(json.dumps(meta));original=packed.read_bytes()
    with gzip.open(packed,'wb') as f:f.write(raw+b'x')
    reject('gzip data mismatch refused',lambda:release(root/'rejected.json'))
    packed.write_bytes(original)
    saved=root/'saved-sidecar';sidecar.rename(saved);sidecar.symlink_to(saved)
    reject('input metadata symlink refused',lambda:release(root/'rejected.json'))
    sidecar.unlink();saved.rename(sidecar)
    packed.rename(root/'saved-gzip');packed.symlink_to(root/'saved-gzip')
    reject('input gzip symlink refused',lambda:release(root/'rejected.json'))
    packed.unlink();(root/'saved-gzip').rename(packed)

    # Run the actual shell orchestration in an isolated tiny project. Compilation
    # and image assembly are stubs; release-manifest.py and gzip are real.
    project=root/'project';source=project/'source/emmc';(source/'boot').mkdir(parents=True)
    shutil.copyfile(HERE/'rebuild.sh',source/'rebuild.sh')
    (source/'release-manifest.py').write_text((HERE/'release-manifest.py').read_text().replace('IMAGE_BYTES = 4580179968','IMAGE_BYTES = 32768'))
    (source/'boot/rebuild-boot.sh').write_text('''#!/bin/sh
set -eu
mkdir -p work/emmc/boot/assets
printf idb > work/emmc/boot/assets/idbloader.img
printf fit > work/emmc/boot/assets/u-boot.itb
''')
    inputfile=project/'sd.img.gz';inputfile.write_bytes(b'pinned-input-fixture')
    (source/'inputs.json').write_text(json.dumps({'sd_compressed':{'bytes':inputfile.stat().st_size,'sha256':hashlib.sha256(inputfile.read_bytes()).hexdigest()}}))
    bindir=root/'bin';bindir.mkdir();docker=bindir/'docker'
    docker.write_text('''#!/usr/bin/env python3
import hashlib,json,pathlib,sys
args=sys.argv[1:]
with pathlib.Path('calls.jsonl').open('a') as f:f.write(json.dumps(args)+'\\n')
if 'source/emmc/kernel/build-dtb.sh' in args:
 p=pathlib.Path('work/emmc/kernel/rk3399-firefly-batocera-emmc.dtb');p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'dtb')
elif 'source/emmc/make-image.py' in args:
 i=args.index('source/emmc/make-image.py');mode=args[i+1];p=pathlib.Path(args[i+3]);data=bytes(range(256))*128;p.write_bytes(data)
 p.with_suffix('.manifest.json').write_text(json.dumps({'image':p.name,'mode':mode,'board':'firefly-rk3399','bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'root_device':'/dev/mmcblk2p1' if mode=='emmc' else '/dev/mmcblk1p1'}))
 if mode=='installer':
  meta=json.loads(pathlib.Path(args[args.index('--payload-manifest')+1]).read_text());assert meta['medium']=='emmc'
elif 'source/emmc/verify-image.py' in args:
 p=pathlib.Path(args[args.index('--image')+1]);mode=args[args.index('--mode')+1]
 sums=(p.parent/'SHA256SUMS').read_text()
 for q in [p,pathlib.Path(str(p)+'.gz')]:assert hashlib.sha256(q.read_bytes()).hexdigest()+'  '+q.name in sums
 report=pathlib.Path(args[args.index('--report')+1]);report.write_text(json.dumps({'result':'PASS','mode':mode}))
else:raise SystemExit('Unexpected docker invocation')
''');docker.chmod(0o755)
    env=dict(os.environ,PATH=str(bindir)+os.pathsep+os.environ['PATH'])
    def run(out,inp=inputfile):
        return subprocess.run(['bash',str(source/'rebuild.sh'),str(inp),str(out)],env=env,capture_output=True,text=True)
    existing=project/'existing';existing.mkdir();(existing/'sentinel').write_text('keep')
    result=run(existing);assert result.returncode and (existing/'sentinel').read_text()=='keep'
    checks.append('existing output directory refused before build')
    outlink=project/'output-link';outlink.symlink_to(existing)
    assert run(outlink).returncode;checks.append('output-directory symlink refused')
    inputlink=project/'input-link';inputlink.symlink_to(inputfile)
    assert run(project/'new',inputlink).returncode;checks.append('input symlink refused before build')
    assert run(root/'outside-project').returncode;checks.append('outside-project output refused')
    bad=project/'bad.gz';bad.write_bytes(b'bad')
    assert run(project/'bad-size',bad).returncode and not (project/'bad-size').exists()
    checks.append('wrong input size refused before output creation')
    bad.write_bytes(b'X'*inputfile.stat().st_size)
    assert run(project/'bad-hash',bad).returncode and not (project/'bad-hash').exists()
    checks.append('wrong input hash refused before output creation')
    assert not (project/'calls.jsonl').exists();checks.append('invalid inputs never invoke build tools')
    out=project/'good'
    result=run(out)
    assert result.returncode==0,(result.stdout,result.stderr)
    assert json.loads((out/'validation/emmc-image.json').read_text())['mode']=='emmc'
    assert json.loads((out/'validation/installer-image.json').read_text())['mode']=='installer'
    checks.append('both final image verifiers invoked after checksum generation')
    calls=[json.loads(x) for x in (project/'calls.jsonl').read_text().splitlines()]
    assert len(calls)==5
    checks.append('kernel assembly and two verifier calls have expected paths')
    assert len((out/'SHA256SUMS').read_text().splitlines())==5
    checks.append('checksum file includes both raw gzip pairs and payload manifest')
    print(result.stdout.strip())
report={'result':'PASS','count':len(checks),'checks':checks,'scope':'Small regular-file release tests; real shell orchestration with explicit compiler/image-builder stubs'}
(HERE/'rebuild-validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
