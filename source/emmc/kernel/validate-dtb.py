#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Validate eMMC boot path and all-property equality with the checked SD DTB."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

SOURCE = Path(__file__).resolve().parent
ROOT = SOURCE.parents[2]
WORK = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'work/emmc/kernel'
SD = WORK / 'rk3399-firefly-batocera-sd.dtb'
DTB = WORK / 'rk3399-firefly-batocera-emmc.dtb'
checks = []


def check(name, actual, expected):
    checks.append({'name':name, 'actual':actual, 'expected':expected, 'pass':actual==expected})


def properties(path):
    data=path.read_bytes()
    magic,total,struct_start,strings_start,_,version,compat,_,strings_size,struct_size=struct.unpack('>10I',data[:40])
    assert magic==0xd00dfeed and total==len(data) and version>=17 and compat<=17
    assert struct_start+struct_size<=total and strings_start+strings_size<=total
    strings=data[strings_start:strings_start+strings_size]
    pos=struct_start
    stack=[]
    props={}
    while pos<struct_start+struct_size:
        token=struct.unpack_from('>I',data,pos)[0];pos+=4
        if token==1:
            end=data.index(b'\0',pos)
            stack.append(data[pos:end].decode())
            pos=(end+4)&~3
        elif token==2:
            stack.pop()
        elif token==3:
            length,nameoff=struct.unpack_from('>II',data,pos);pos+=8
            assert nameoff<len(strings)
            name=strings[nameoff:strings.index(b'\0',nameoff)].decode()
            node='/'+'/'.join(stack[1:])
            assert (node,name) not in props
            props[node,name]=data[pos:pos+length]
            pos=(pos+length+3)&~3
        elif token==4:
            pass
        elif token==9:
            assert not stack
            return props
        else:
            raise ValueError('Invalid DTB token: '+str(token))
    raise ValueError('Missing DTB end')


def get(node,prop,kind='s'):
    return subprocess.check_output(['fdtget','-t',kind,str(DTB),node,prop],text=True).strip()


def u32(v):
    return struct.pack('>I',v)


sd,emmc=properties(SD),properties(DTB)
inputs=json.loads((SOURCE/'inputs.json').read_text())
check('SD baseline hash',hashlib.sha256(SD.read_bytes()).hexdigest(),inputs['sd_reference_dtb_sha256'])
expected_changes={
    ('/mmc@fe330000','status'):(b'disabled\0',b'okay\0'),
    ('/syscon@ff770000/phy@f780','status'):(b'disabled\0',b'okay\0'),
    ('/mmc@fe330000','mmc-hs400-1_8v'):(b'',None),
    ('/mmc@fe330000','mmc-hs400-enhanced-strobe'):(b'',None),
    ('/mmc@fe330000','mmc-hs200-1_8v'):(None,b''),
    ('/mmc@fe330000','max-frequency'):(None,u32(200000000)),
}
actual_changes={key:(sd.get(key),emmc.get(key)) for key in sd.keys()|emmc.keys() if sd.get(key)!=emmc.get(key)}
check('Only six expected eMMC properties differ',
      {str(k):[None if v is None else v.hex() for v in values] for k,values in sorted(actual_changes.items())},
      {str(k):[None if v is None else v.hex() for v in values] for k,values in sorted(expected_changes.items())})
for node,prop,expected,kind in [
    ('/','model','Firefly-RK3399 Board','s'),
    ('/','compatible','firefly,firefly-rk3399 rockchip,rk3399','s'),
    ('/aliases','mmc0','/mmc@fe310000','s'),
    ('/aliases','mmc1','/mmc@fe320000','s'),
    ('/aliases','mmc2','/mmc@fe330000','s'),
    ('/mmc@fe330000','compatible','rockchip,rk3399-sdhci-5.1 arasan,sdhci-5.1','s'),
    ('/mmc@fe330000','status','okay','s'),
    ('/mmc@fe330000','bus-width','8','u'),
    ('/mmc@fe330000','max-frequency','200000000','u'),
    ('/mmc@fe330000','phy-names','phy_arasan','s'),
    ('/syscon@ff770000/phy@f780','status','okay','s'),
    ('/syscon@ff770000/phy@f780','compatible','rockchip,rk3399-emmc-phy','s'),
    ('/mmc@fe320000','status','okay','s'),
    ('/mmc@fe310000','status','okay','s'),
    ('/hdmi-sound','status','okay','s'),
    ('/thermal-zones/cpu-thermal/trips/cpu_crit','temperature','95000','u'),
]:
    check(node+':'+prop,get(node,prop,kind),expected)
for prop in ['non-removable','mmc-hs200-1_8v']:
    check('eMMC '+prop,emmc.get(('/mmc@fe330000',prop)),b'')
for prop in ['mmc-hs400-1_8v','mmc-hs400-enhanced-strobe','mmc-hs200-1_2v','mmc-hs400-1_2v']:
    check('eMMC lacks '+prop,('/mmc@fe330000',prop) in emmc,False)
check('eMMC PHY phandle',get('/mmc@fe330000','phys','u'),get('/syscon@ff770000/phy@f780','phandle','u'))
check('eMMC clock provider',get('/syscon@ff770000/phy@f780','clocks','u'),get('/mmc@fe330000','phandle','u'))
config=dict(line.split('=',1) for line in (ROOT/'source/kernel/base-kernel.config').read_text().splitlines() if line.startswith('CONFIG_') and '=' in line)
for symbol in ['MMC','MMC_BLOCK','MMC_SDHCI','MMC_SDHCI_PLTFM','MMC_SDHCI_OF_ARASAN','PHY_ROCKCHIP_EMMC','REGULATOR_FIXED_VOLTAGE','REGULATOR_RK808','MFD_RK8XX','MFD_RK8XX_I2C','ROCKCHIP_PM_DOMAINS']:
    check('CONFIG_'+symbol+' built-in',config.get('CONFIG_'+symbol),'y')
host=(ROOT/'source/docs/integration-evidence/mmc-host-6.6.27.c').read_text()
block=(ROOT/'source/docs/integration-evidence/mmc-block-6.6.27.c').read_text()
check('Linux uses MMC DT alias for host index','of_alias_get_id(dev->of_node, "mmc")' in host and 'index = alias_id;' in host and 'host->index = index;' in host,True)
check('Linux block name follows host index','"mmcblk%u%s", card->host->index' in block,True)
for item in checks:
    for key in ['actual','expected']:
        if isinstance(item[key],bytes):item[key]=item[key].hex()
result={'result':'PASS' if all(i['pass'] for i in checks) else 'FAIL','passed':sum(i['pass'] for i in checks),'total':len(checks),'dtb':DTB.name,'bytes':DTB.stat().st_size,'sha256':hashlib.sha256(DTB.read_bytes()).hexdigest(),'unchanged_properties':len(set(sd)&set(emmc))-sum(k in sd and k in emmc for k in actual_changes),'changed_properties':len(actual_changes),'root_device':'/dev/mmcblk2p1','checks':checks}
(WORK/'validation.json').write_text(json.dumps(result,indent=2)+'\n')
for item in checks:
    if not item['pass']:print('FAIL',item)
print('eMMC DTB:',result['passed'], '/',result['total'],result['result'])
sys.exit(0 if result['result']=='PASS' else 1)
