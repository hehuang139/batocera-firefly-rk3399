#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
import importlib.util,json,os,pathlib,struct,subprocess,tempfile,hashlib
script=pathlib.Path(__file__).resolve().with_name('zero-free-fat.py')
spec=importlib.util.spec_from_file_location('zero_fat',script);z=importlib.util.module_from_spec(spec);spec.loader.exec_module(z)
checks=[]
def check(name,condition):
    assert condition,name
    checks.append(name)
with tempfile.TemporaryDirectory(prefix='firefly-fat-fixture-') as tmp:
    tmp=pathlib.Path(tmp);image=tmp/'fixture.img'
    size=4580179968;start=32768*512;fat_size=8176*512;fat_start=start+32*512;data_start=fat_start+2*fat_size
    count=(8388576-32-2*8176)//8;data_end=data_start+count*4096
    raw=bytearray(512);raw[510:]=b'\x55\xaa';struct.pack_into('<B3sB3sII',raw,446,0x80,bytes(3),0x0c,bytes(3),32768,8388608)
    struct.pack_into('<B3sB3sII',raw,462,0,bytes(3),0x83,bytes(3),8421376,524288)
    boot=bytearray(512);struct.pack_into('<H',boot,11,512);boot[13]=8;struct.pack_into('<H',boot,14,32);boot[16]=2
    struct.pack_into('<II',boot,32,8388576,8176);struct.pack_into('<I',boot,44,2);boot[71:82]=b'BATOCERA   ';boot[82:90]=b'FAT32   ';boot[510:]=b'\x55\xaa'
    fat=bytearray(struct.pack('<I',0x0fffffff)*(fat_size//4));free=[3,4,9,count+1]
    for n in free:struct.pack_into('<I',fat,n*4,0)
    # Padding entries marked free must never extend the write range past data_end.
    for n in range(count+2,fat_size//4):struct.pack_into('<I',fat,n*4,0)
    with image.open('w+b') as f:
        f.truncate(size);f.write(raw);f.seek(start);f.write(boot);f.seek(fat_start);f.write(fat);f.write(fat)
        for n in free:f.seek(data_start+(n-2)*4096);f.write(b'F'*4096)
        f.seek(data_start+3*4096);f.write(b'ALLOCATED'+bytes(4087))
        f.seek(data_end);f.write(b'BPB-TAIL-MUST-STAY')
        f.seek((32768+8388608)*512+1024);f.write(b'SHARE-MUST-STAY')
    def run(*flags,success=True):
        r=subprocess.run(['python3',str(script),str(image),*flags],capture_output=True,text=True)
        check('command '+(' '.join(flags) or 'zero')+' '+str(len(checks)),(r.returncode==0)==success)
        return json.loads(r.stdout) if success else r
    info=run('--check-only');check('free cluster bytes',info['free_bytes']==len(free)*4096);check('merged contiguous runs',info['free_runs']==3)
    run('--verify',success=False)
    # A mismatched mirror is rejected before touching even the first free cluster.
    with image.open('r+b') as f:f.seek(fat_start+fat_size+8);f.write(bytes(4))
    r=run(success=False);check('mismatched FAT copies are rejected','two FAT copies differ' in r.stderr)
    with image.open('r+b') as f:
        f.seek(data_start+4096);check('failed preflight left data unchanged',f.read(4096)==b'F'*4096)
        f.seek(fat_start+fat_size);f.write(fat)
    result=run();check('protected byte digest unchanged',result['protected_sha256_before']==result['protected_sha256_after']);check('all free clusters zero',result['all_free_clusters_zero'])
    run('--verify')
    with image.open('rb') as f:
        f.seek(0);check('MBR unchanged',f.read(512)==raw)
        f.seek(start);check('BPB unchanged',f.read(512)==boot)
        f.seek(fat_start);check('both FATs unchanged',f.read(fat_size*2)==fat+fat)
        f.seek(data_start+3*4096);check('allocated cluster unchanged',f.read(9)==b'ALLOCATED')
        f.seek(data_end);check('padding outside valid clusters unchanged',f.read(18)==b'BPB-TAIL-MUST-STAY')
        f.seek((32768+8388608)*512+1024);check('SHARE unchanged',f.read(15)==b'SHARE-MUST-STAY')
    link=tmp/'link.img';link.symlink_to(image)
    r=subprocess.run(['python3',str(script),str(link)],capture_output=True,text=True);check('symlink rejected',r.returncode!=0 and 'regular .img' in r.stderr)
    r=subprocess.run(['python3',str(script),'/dev/null'],capture_output=True,text=True);check('character device rejected',r.returncode!=0 and 'regular .img' in r.stderr)
report={'result':'PASS','count':len(checks),'checks':checks,'zero_result':result,'script_sha256':hashlib.sha256(script.read_bytes()).hexdigest()}
print(json.dumps(report,indent=2))
