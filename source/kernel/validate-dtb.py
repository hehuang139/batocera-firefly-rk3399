#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Validate boot-critical Firefly board properties in the compiled DTB."""
import hashlib
import json
import pathlib
import subprocess
import sys
src = pathlib.Path(__file__).resolve().parent
root = src.parent.parent
dtb = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else root/'work/kernel/rk3399-firefly-batocera-sd.dtb'
config = src/'base-kernel.config'
checks = []
def get(node, prop, kind='s'):
    return subprocess.check_output(['fdtget', '-t', kind, str(dtb), node, prop], text=True).strip()
def check(name, actual, expected):
    checks.append({'name':name, 'actual':actual, 'expected':expected, 'pass':actual == expected})
def status(node, expected='okay'):
    check(node + ' status', get(node, 'status'), expected)
check('board compatible', get('/', 'compatible'), 'firefly,firefly-rk3399 rockchip,rk3399')
check('board model', get('/', 'model'), 'Firefly-RK3399 Board')
check('SD alias', get('/aliases', 'mmc1'), '/mmc@fe320000')
check('SDIO alias', get('/aliases', 'mmc0'), '/mmc@fe310000')
check('UART console', get('/chosen', 'stdout-path'), 'serial2:1500000n8')
for node in ['/mmc@fe320000','/mmc@fe310000','/ethernet@fe300000','/hdmi@ff940000',
             '/hdmi-sound','/i2s@ff8a0000','/gpu@ff9a0000','/vop@ff900000',
             '/vop@ff8f0000','/usb@fe380000','/usb@fe3a0000','/usb@fe3c0000',
             '/usb@fe3e0000','/usb@fe800000','/usb@fe800000/usb@fe800000',
             '/usb@fe900000','/usb@fe900000/usb@fe900000','/serial@ff180000',
             '/i2c@ff3c0000']:
    status(node)
status('/mmc@fe330000','disabled')
status('/syscon@ff770000/phy@f780','disabled')
check('USB3 host',get('/usb@fe900000/usb@fe900000','dr_mode'),'host')
check('USB-C role',get('/usb@fe800000/usb@fe800000','dr_mode'),'otg')
check('FUSB302 match',get('/i2c@ff3d0000/typec-portc@22','compatible'),'fairchild,fusb302')
for trip, temp in [('cpu_alert0',70000),('cpu_alert1',75000),('cpu_crit',95000)]:
    check('CPU thermal '+trip,get('/thermal-zones/cpu-thermal/trips/'+trip,'temperature','u'),str(temp))
bt='/serial@ff180000/bluetooth'
check('BT driver',get(bt,'compatible'),'brcm,bcm43438-bt')
check('BT max speed',get(bt,'max-speed','u'),'4000000')
for prop, gpio, pin in [('shutdown-gpios','/pinctrl/gpio@ff720000',9),
                        ('host-wakeup-gpios','/pinctrl/gpio@ff720000',4),
                        ('device-wakeup-gpios','/pinctrl/gpio@ff780000',26)]:
    expected=f"{get(gpio,'phandle','u')} {pin} 0"
    check('BT '+prop,get(bt,prop,'u'),expected)
check('SDIO Wifi IRQ type',get('/mmc@fe310000/wifi@1','interrupts','u'),'3 4')
check('USB hub reset',get('/pinctrl/usb2/hub-rst','rockchip,pins','u').split()[:3],['2','4','0'])
check('heartbeat',get('/leds/led-0','linux,default-trigger'),'heartbeat')
config_text=config.read_text()
required='ARCH_ROCKCHIP MMC_DW MMC_DW_ROCKCHIP PWRSEQ_SIMPLE MFD_RK8XX MFD_RK8XX_I2C REGULATOR_RK808 REGULATOR_FAN53555 DWMAC_ROCKCHIP PHYLIB ROCKCHIP_IODOMAIN ROCKCHIP_PM_DOMAINS ROCKCHIP_THERMAL ROCKCHIP_IOMMU DRM_ROCKCHIP ROCKCHIP_DW_HDMI DRM_PANFROST DRM_DW_HDMI_I2S_AUDIO SND_SOC_HDMI_CODEC SND_SOC_ROCKCHIP_I2S SND_SIMPLE_CARD USB_EHCI_HCD_PLATFORM USB_OHCI_HCD_PLATFORM USB_XHCI_PLATFORM USB_DWC3 PHY_ROCKCHIP_INNO_USB2 PHY_ROCKCHIP_TYPEC BRCMFMAC BRCMFMAC_SDIO BT_HCIUART BT_HCIUART_SERDEV BT_HCIUART_BCM SERIAL_8250_DW TYPEC_TCPM TYPEC_FUSB302 HID_GENERIC USB_HID JOYSTICK_XPAD EXT4_FS SQUASHFS SQUASHFS_ZSTD OVERLAY_FS'.split()
for symbol in required:
    value=next((line.split('=',1)[1] for line in config_text.splitlines() if line.startswith('CONFIG_'+symbol+'=')),'disabled')
    checks.append({'name':'CONFIG_'+symbol,'actual':value,'expected':'y or m','pass':value in ['y','m']})
result={'dtb':dtb.name,'dtb_sha256':hashlib.sha256(dtb.read_bytes()).hexdigest(),
        'kernel_config_sha256':hashlib.sha256(config.read_bytes()).hexdigest(),
        'checks':checks,'passed':sum(x['pass'] for x in checks),'total':len(checks),
        'limitations':['HDMI-CEC driver is disabled in the base kernel.','RT5640 analog audio codec driver is disabled in the base kernel.','On-board Realtek Ethernet PHY uses generic PHY handling; confirm link speed on hardware.']}
(root/'work/kernel/validation.json').write_text(json.dumps(result,indent=2)+'\n')
for x in checks:
    if not x['pass']: print('FAIL',x)
print(f"DTB and kernel configuration: {result['passed']}/{result['total']} PASS")
sys.exit(0 if all(x['pass'] for x in checks) else 1)
