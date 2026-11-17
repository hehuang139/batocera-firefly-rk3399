import gzip,hashlib,importlib.util,json,os,subprocess,sys,tarfile,tempfile
from pathlib import Path
sys.dont_write_bytecode=True
SOURCE=Path('/archives/firefly-rk3399-batocera/source/v431/rebuild.py')
spec=importlib.util.spec_from_file_location('rebuild_fixture',SOURCE);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
pin=lambda p:{'bytes':p.stat().st_size,'sha256':sha(p)}
results=[]
with tempfile.TemporaryDirectory(prefix='rebuild431-review-') as directory:
 project=Path(directory)/'project';here=project/'source/v431';(here/'provenance').mkdir(parents=True);(here/'assets').mkdir()
 upstream=Path(directory)/'inputs';upstream.mkdir();bsp40=upstream/'bsp40.img.gz';userspace=upstream/'431.tar.xz'
 with gzip.open(bsp40,'wb') as f:f.write(b'fake-bsp-raw-image')
 with tarfile.open(userspace,'w:xz') as t:
  for member,data in [('boot/batocera.update',b'primary'),('boot/rufomaculata.update',b'secondary'),('boot/initrd.lz4',b'initrd')]:
   p=upstream/Path(member).name;p.write_bytes(data);t.add(p,arcname=member)
 (project/'source/base-manifest.json').write_text(json.dumps(pin(bsp40)))
 (here/'provenance/base-manifest.json').write_text(json.dumps(pin(userspace)))
 components={}
 for name,data in [('secondary',b'secondary'),('initrd',b'initrd')]:
  p=here/'assets'/name;p.write_bytes(data);components[name]={'path':p.relative_to(project).as_posix(),**pin(p)}
 system=upstream/'system';system.write_bytes(b'system')
 (here/'inputs.json').write_text(json.dumps({'version':'43.1','components':components,'documents':{},'boot_assets':{},'rootfs':pin(system)}))
 filetime=1780000000000000000
 (here/'provenance/final-content.json').write_text(json.dumps({'files':{'.':{'mtime':filetime},'one':{'mtime':filetime}}}))
 m.ROOT=project;m.HERE=here;m.os.geteuid=lambda:0
 calls=[]
 def run(*args):
  argv=[str(x) for x in args];calls.append(argv)
  command=Path(argv[0]).name
  if command=='mcopy':Path(argv[-1]).write_bytes(b'squashfs')
  elif command=='unsquashfs':
   target=Path(argv[argv.index('-d')+1]);target.mkdir()
   if target.name=='rootfs':(target/'one').write_bytes(b'unchanged')
  elif command=='mksquashfs':Path(argv[2]).write_bytes(b'system')
  elif command=='gzip':
   raw=Path(argv[-1]);Path(str(raw)+'.gz').write_bytes(gzip.compress(raw.read_bytes(),mtime=0))
  elif len(argv)>1:
   script=Path(argv[1]).name
   if script=='make-image.py':
    image=Path(argv[4]);image.write_bytes(b'fake-image');image.with_suffix('.manifest.json').write_text('{}')
   elif script=='release-manifest.py':Path(argv[3]).write_text('{}')
 m.run=run
 out=project/'outputs/review';scratch=Path(directory)/'scratch'
 sys.argv=[str(SOURCE),str(bsp40),str(userspace),str(out),'--scratch',str(scratch)];m.main()
 assert (out/'SHA256SUMS').is_file()
 assert len([c for c in calls if len(c)>1 and Path(c[1]).name=='verify-image.py'])==2
 for script in ['apply.py','validate.py']:
  actual=next(c for c in calls if len(c)>1 and Path(c[1]).name==script)
  subprocess.run([sys.executable,str(SOURCE.parent/'rootfs'/script),'--rootfs',str(scratch/'rootfs'),'--bsp-rootfs',str(scratch/'bsp-rootfs'),'--report',str(out/'dummy'),'--help'],check=True,stdout=subprocess.DEVNULL)
  assert all(x in actual for x in ['--rootfs','--bsp-rootfs','--report'])
 assert (scratch/'rootfs/one').stat().st_mtime_ns==filetime
 assert (scratch/'rufomaculata').read_bytes()==b'secondary'
 assert (scratch/'initrd.lz4').read_bytes()==b'initrd'
 before_commands=len(calls)
 rootonly=project/'outputs/rootfs-only';rootscratch=Path(directory)/'scratch-only'
 sys.argv=[str(SOURCE),str(bsp40),str(userspace),str(rootonly),'--scratch',str(rootscratch),'--rootfs-only'];m.main()
 onlycalls=calls[before_commands:]
 assert any(len(c)>1 and Path(c[1]).name=='verify-packed-rootfs.py' for c in onlycalls)
 assert not any(len(c)>1 and Path(c[1]).name=='make-image.py' for c in onlycalls)
 results.append({'name':'rootfs_only_boundary','result':'PASS','details':'Exact system pin and packed verifier reached; no disk assembly call'})
 results.append({'name':'orchestration_fixture','result':'PASS','details':['actual CLI flags accepted by apply/validate parsers','both upstream layers/initrd extracted and pinned','timestamps restored','system hash check and two image verification calls reached'],'commands':calls})
 def fails(output,scr,needle):
  before=len(calls);sys.argv=[str(SOURCE),str(bsp40),str(userspace),str(output),'--scratch',str(scr)]
  try:m.main()
  except (SystemExit,ValueError) as e:pass
  else:raise AssertionError('Expected failure: '+needle)
  assert len(calls)==before,'Commands run before rejection'
 # Input pins are reread on each run, before any output mutation.
 outside=Path(directory)/'outside';fails(outside,Path(directory)/'scratch2','outside-output');assert not outside.exists()
 fails(out,Path(directory)/'scratch2','existing-output')
 link=project/'linked';link.symlink_to(outside);fails(link,Path(directory)/'scratch2','dangling-output-link')
 nested=project/'outputs/new';fails(nested,nested/'scratch','overlapping');assert not nested.exists()
 invalid=project/'outputs/bad-input';bsp40.write_bytes(b'tampered');fails(invalid,Path(directory)/'scratch3','input-pin');assert not invalid.exists()
 results.append({'name':'prewrite_boundary_fixtures','result':'PASS','cases':['output outside project','existing output','dangling output symlink','output/scratch overlap','wrong upstream hash']})
report={'result':'PASS','scope':'Small ordinary-file fixture; expensive external image tools mocked; actual apply/validate --help parsers executed. Source review also covers metadata and pinned source flow.','source_sha256':sha(SOURCE),'checks':results}
Path('/home/hehuang/Documents/Codex/2026-11-02/firefly-x20/work/batocera431-research/port/rebuild-fixture-result.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'result':'PASS','fixture_groups':len(results),'source_sha256':sha(SOURCE)}))
