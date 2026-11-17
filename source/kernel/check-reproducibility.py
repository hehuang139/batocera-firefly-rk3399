#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
import hashlib,json,pathlib,re,subprocess
root=pathlib.Path(__file__).resolve().parents[2]
work=root/'work/kernel'
before=hashlib.sha256((work/'rk3399-firefly-batocera-sd.dtb').read_bytes()).hexdigest()
rebuilt=subprocess.run(['bash',str(root/'source/kernel/build-dtb.sh')],capture_output=True,text=True,check=True)
after=hashlib.sha256((work/'rk3399-firefly-batocera-sd.dtb').read_bytes()).hexdigest()
assert before==after
base=work/'tree/arch/arm64/boot/dts/rockchip'
pre=subprocess.run(['gcc','-E','-nostdinc','-undef','-D__DTS__','-x','assembler-with-cpp','-I',str(work/'tree/include'),'-I',str(base),str(base/'rk3399-firefly.dts')],capture_output=True,check=True)
(work/'upstream-firefly.pp.dts').write_bytes(pre.stdout)
res=subprocess.run(['dtc','-I','dts','-O','dtb','-o',str(work/'upstream-firefly.dtb'),str(work/'upstream-firefly.pp.dts')],capture_output=True,text=True,check=True)
def warnings(text):
    return sorted(set(re.findall(r'Warning \(([^)]+)\): ([^:\n]+)',text)))
base_warnings=warnings(res.stderr)
changed_warnings=warnings(rebuilt.stderr)
assert base_warnings==changed_warnings,(base_warnings,changed_warnings)
result={'deterministic_rebuild':True,'sha256':after,'upstream_warning_signatures':base_warnings,'adapted_warning_signatures':changed_warnings,'new_warning_signatures':[],'compiler':subprocess.check_output(['dtc','--version'],text=True).strip()}
(work/'reproducibility.json').write_text(json.dumps(result,indent=2)+'\n')
print('Identical DTB after clean-source reconstruction; warning signatures match upstream baseline:',len(base_warnings))
