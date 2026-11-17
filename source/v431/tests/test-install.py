#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Offline installer tests: regular temporary files only, no hardware writes."""
import sys
sys.dont_write_bytecode = True
import copy
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import struct
import tempfile
import subprocess
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('installer', HERE.parent/'assets/install-to-emmc.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
checks = []


def success(name, fn):
    fn()
    checks.append(name)


def rejects(name, fn):
    try:
        fn()
    except (ValueError, OSError):
        checks.append(name)
    else:
        raise AssertionError(name+' was accepted')


with tempfile.TemporaryDirectory(prefix='firefly-installer-test-') as tmp:
    root = Path(tmp)
    sysroot = root/'mmcblk2'
    (sysroot/'holders').mkdir(parents=True)
    m.SYS = sysroot
    actual_read = Path.read_text
    def mock_read(path, *args, **kwargs):
        if path == Path('/proc/swaps'):
            return 'Filename Type Size Used Priority\n'
        return actual_read(path, *args, **kwargs)
    info = {'compatible':[b'firefly,firefly-rk3399', b'rockchip,rk3399'],
            'model':'Firefly-RK3399 Board', 'path':'/sys/devices/platform/fe330000.mmc/mmc_host/mmc2/mmc2:0001/block/mmcblk2',
            'type':'MMC', 'cid':'0123456789abcdef'*2, 'name':'test', 'removable':'0', 'ro':'0',
            'sector':512, 'bytes':8*1024**3, 'dev':'179:64',
            'boot':[{'source':'/dev/mmcblk1p1'}], 'userdata':[{'source':'/dev/mmcblk1p2'}],
            'boot_sys':'/sys/devices/platform/fe320000.mmc/mmc_host/mmc1/mmc1:0001/block/mmcblk1/mmcblk1p1',
            'userdata_sys':'/sys/devices/platform/fe320000.mmc/mmc_host/mmc1/mmc1:0001/block/mmcblk1/mmcblk1p2',
            'target_mounts':[]}
    with patch.object(Path, 'read_text', mock_read):
        success('valid TF boot and original Firefly eMMC accepted', lambda:m.validate_identity(info))
        for key,value in [('compatible',[b'pine64,rockpro64']),('model','ROC-RK3399-PC'),('type','SD'),
                          ('path','/platform/fe320000.mmc/block/mmcblk2'),('removable','1'),('ro','1'),
                          ('sector',4096),('bytes',4*1024**3),('cid','123'),('boot_sys',info['userdata_sys']),
                          ('userdata_sys','/sys/devices/fe330000.mmc/mmcblk2/mmcblk2p2'),
                          ('target_mounts',[{'point':'/userdata'}])]:
            changed=copy.deepcopy(info);changed[key]=value
            rejects('reject invalid '+key,lambda:m.validate_identity(changed))
        changed=copy.deepcopy(info);changed['target_mounts']=[{'point':'/media/OLD SYSTEM'}]
        success('ordinary old-system automount is eligible for unmount',lambda:m.validate_identity(changed))
        (sysroot/'holders/dm-0').touch()
        rejects('active device-mapper holder rejected',lambda:m.validate_identity(info))
        (sysroot/'holders/dm-0').unlink()
    fake_swap = root/'swapfile';fake_swap.touch()
    def swap_read(path,*args,**kwargs):
        if path == Path('/proc/swaps'):
            return f'Filename Type Size Used Priority\n{fake_swap} file 1 0 -2\n'
        return actual_read(path,*args,**kwargs)
    with patch.object(Path,'read_text',swap_read),patch.object(m,'dev_sys_path',return_value=info['path']):
        rejects('swap file on eMMC rejected',lambda:m.validate_identity(info))
    orig_stat = Path.stat
    class BlockStat:
        st_mode=stat.S_IFBLK|0o600
        st_rdev=os.makedev(179,64)
        st_dev=os.makedev(0,6)
    def alias_stat(path,*args,**kwargs):
        if path==fake_swap:return BlockStat()
        return orig_stat(path,*args,**kwargs)
    resolved=[]
    def resolve_swap(dev):
        resolved.append(dev)
        return info['path']
    with patch.object(Path,'read_text',swap_read),patch.object(Path,'stat',alias_stat),patch.object(m,'dev_sys_path',resolve_swap):
        rejects('block-device alias swap on eMMC rejected',lambda:m.validate_identity(info))
    assert resolved==['179:64'];checks.append('block alias resolved using st_rdev')
    rows=m.mounts('42 1 0:65 / /media/OLD\\040SYSTEM rw - fuseblk /dev/mmcblk2p3 rw\n')
    assert rows[0]['point']=='/media/OLD SYSTEM';checks.append('mount paths with escaped spaces parsed')
    success('FUSE eMMC mount detected by block source', lambda: (_ for _ in ()).throw(AssertionError()) if len(m.target_mounts(rows))!=1 else None)
    fuse_alias=[{'device':'0:65','point':'/media/OLD SYSTEM','type':'fuseblk','source':str(fake_swap)}]
    with patch.object(Path,'stat',alias_stat),patch.object(m,'dev_sys_path',return_value=info['path']):
        assert len(m.target_mounts(fuse_alias))==1
        checks.append('FUSE block source alias resolved by st_rdev')
    with patch.object(Path,'stat',alias_stat),patch.object(m,'dev_sys_path',return_value=info['userdata_sys']):
        assert not m.target_mounts(fuse_alias)
        checks.append('non-target FUSE alias is left alone')
    source=root/'image.img.gz'
    raw=bytearray(8192)
    raw[510:512]=b'\x55\xaa'
    for i,(typ,start,count) in enumerate([(12,32768,8388608),(131,8421376,524288)]):
        raw[446+i*16:462+i*16]=struct.pack('<B3sB3sII',0,b'\0'*3,typ,b'\0'*3,start,count)
    raw[512:]=bytes(range(256))*30
    with gzip.open(source,'wb') as f:f.write(raw)
    m.IMAGE_BYTES=len(raw)
    manifest={'board':'firefly-rk3399','medium':'emmc',
              'image':{'name':'image.img','bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()},
              'compressed':{'name':source.name,'bytes':source.stat().st_size,'sha256':hashlib.sha256(source.read_bytes()).hexdigest()}}
    success('valid eMMC manifest accepted',lambda:m.validate_manifest(manifest,source))
    wrong=copy.deepcopy(manifest);wrong['medium']='sd'
    rejects('SD manifest refused',lambda:m.validate_manifest(wrong,source))
    success('compressed and raw image verified including MBR',lambda:m.verify_source(source,manifest))
    wrong=copy.deepcopy(manifest);wrong['compressed']['sha256']='0'*64
    rejects('compressed hash mismatch refused',lambda:m.verify_source(source,wrong))
    wrong=copy.deepcopy(manifest);wrong['image']['sha256']='0'*64
    rejects('raw hash mismatch refused',lambda:m.verify_source(source,wrong))
    link=root/'link';link.symlink_to(source)
    rejects('symlink image refused',lambda:m.regular(link))
    rejects('device input refused',lambda:m.regular(Path('/dev/null')))
    target=root/'ordinary-test-target';capacity=4*1024**2
    target.write_bytes(b'X'*capacity)
    fd=os.open(target,os.O_RDWR)
    try:
        m.write_payload(fd,source,manifest,capacity)
        success('full readback after write and GPT tail clearing',lambda:m.readback(fd,manifest,capacity,flush=False))
        assert os.pread(fd,100,len(raw))==b'X'*100
        checks.append('gap between image and tail remains unchanged')
        os.pwrite(fd,b'Q',100)
        rejects('readback corruption detected',lambda:m.readback(fd,manifest,capacity,flush=False))
    finally:os.close(fd)
    class PartialWrite:
        def __init__(self):self.output=bytearray()
        def __call__(self,fd,data):
            piece=data[:3];self.output.extend(piece);return len(piece)
    partial=PartialWrite()
    with patch.object(os,'write',partial):m.write_all(99,b'abcdefghij')
    assert partial.output==b'abcdefghij';checks.append('partial writes retried without data loss')
    backupdir=root/'backup'
    backupdir.mkdir()
    backup_input=root/'backup-input'
    backup_input.write_bytes(bytes(range(256))*256)
    fd=os.open(backup_input,os.O_RDONLY)
    small_info={'bytes':backup_input.stat().st_size,'cid':info['cid']}
    fake_mount=[{'point':str(root),'type':'ext4','device':'179:33','source':'/dev/mmcblk1p2'}]
    try:
        with patch.object(m,'mounts',return_value=fake_mount),patch.object(m,'dev_sys_path',return_value=info['userdata_sys']):
            saved=m.backup(fd,backupdir,small_info)
        assert Path(saved['path']).read_bytes()==backup_input.read_bytes()
        assert json.loads(Path(saved['path']).with_suffix('.json').read_text())['sha256']==saved['sha256']
        checks.append('full backup bytes and metadata independently verified')
        with patch.object(m,'mounts',return_value=[dict(fake_mount[0],type='vfat')]),patch.object(m,'dev_sys_path',return_value=info['userdata_sys']):
            rejects('backup to FAT filesystem refused',lambda:m.backup(fd,backupdir,small_info))
        with patch.object(m,'mounts',return_value=fake_mount),patch.object(m,'dev_sys_path',return_value=info['path']):
            rejects('backup to target eMMC refused',lambda:m.backup(fd,backupdir,small_info))
    finally:os.close(fd)
    script=str(HERE.parent/'assets/install-to-emmc.py')
    missing=subprocess.run([os.sys.executable,script,'--write'],capture_output=True,text=True)
    assert missing.returncode==2 and '--write requires' in missing.stderr
    checks.append('write without explicit backup choice refused before device access')
    collision=subprocess.run([os.sys.executable,script,'--write','--no-backup','--backup-dir',str(backupdir)],capture_output=True,text=True)
    assert collision.returncode==2
    checks.append('conflicting backup choices refused before device access')
report={'result':'PASS','count':len(checks),'checks':checks,'environment':'Offline Python tests with regular temporary files; no block device written'}
(HERE/'installer-validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
