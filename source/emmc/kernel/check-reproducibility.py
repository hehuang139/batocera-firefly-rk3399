#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Rebuild only in the independent eMMC work tree and compare both DTBs."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

SOURCE=Path(__file__).resolve().parent
ROOT=SOURCE.parents[2]
WORK=ROOT/'work/emmc/kernel'
DTB=WORK/'rk3399-firefly-batocera-emmc.dtb'
before=hashlib.sha256(DTB.read_bytes()).hexdigest()
rebuild=subprocess.run(['bash',str(SOURCE/'build-dtb.sh')],capture_output=True,text=True,check=True)
after=hashlib.sha256(DTB.read_bytes()).hexdigest()
assert before==after

def signatures(name):
    result=subprocess.run(['dtc','-I','dts','-O','dtb','-o','/dev/null',str(WORK/(name+'.pp.dts'))],capture_output=True,text=True,check=True)
    return sorted(set(re.findall(r'Warning \(([^)]+)\): ([^:\n]+)',result.stderr)))
sd=signatures('rk3399-firefly-batocera-sd')
emmc=signatures('rk3399-firefly-batocera-emmc')
assert sd==emmc,(sd,emmc)
report={'result':'PASS','deterministic_rebuild':True,'sha256':after,'bytes':DTB.stat().st_size,'sd_warning_signatures':sd,'emmc_warning_signatures':emmc,'new_warning_signatures':[],'compiler':subprocess.check_output(['dtc','--version'],text=True).strip()}
(WORK/'reproducibility.json').write_text(json.dumps(report,indent=2)+'\n')
print('eMMC DTB rebuild hash matches; warning signatures unchanged:',len(sd))
