"""Verify appearance bounds, saving, reloading and optional physical reboot.

Restores the user's appearance after checking nondefault values through reboot.
"""
import argparse
import json
from pathlib import Path
import re
import time
from mochi_device import Device

ROOT=Path(__file__).resolve().parents[1]
FIELDS=('outfit','color','expression','motion')
COUNTS=(12,6,8,3)

def read(device):
    return {k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',device.command('@appearance','@appearance '))}

def saved(device):
    deadline=time.monotonic()+8
    while time.monotonic()<deadline:
        result=read(device)
        if result['saved']:return result
        time.sleep(.15)
    raise RuntimeError('Appearance was not saved')

def reboot_check(port,before):
    marker={key:count-1 if before[key]!=count-1 else 0 for key,count in zip(FIELDS,COUNTS)}
    result={'reboot_marker':marker}
    try:
        with Device(port) as device:
            for field,key in enumerate(FIELDS):
                assert device.command(f'@appearance-set {field} {marker[key]}','@appearance_set ').endswith('ok')
            stored=saved(device)
            assert all(stored[k]==marker[k] for k in FIELDS)
            assert device.command('@restart','@mochi_restart ')=='@mochi_restart queued'
        deadline=time.monotonic()+75;last=None
        while time.monotonic()<deadline:
            time.sleep(2)
            try:
                with Device(port) as device:
                    firmware=device.command('@firmware','@mochi_firmware ',timeout=4)
                    after=read(device)
                    assert 'state=2' in firmware,firmware
                    assert all(after[k]==marker[k] for k in FIELDS) and after['saved'],after
                    result.update(after_reboot=after,firmware_after_reboot=firmware,physical_reboot=True)
                break
            except (OSError,TimeoutError) as error:last=error
        else:raise RuntimeError('Board did not return after reboot') from last
    finally:
        with Device(port) as device:
            for field,key in enumerate(FIELDS):
                device.command(f'@appearance-set {field} {before[key]}','@appearance_set ')
            after=saved(device)
            assert all(after[k]==before[k] for k in FIELDS)
            device.port.write(b'@close\n@emote idle\n')
            result['original_restored']=True
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',default='COM3')
    parser.add_argument('--reboot',action='store_true')
    parser.add_argument('--output',type=Path,default=ROOT/'.runtime/mochi-appearance-check.json')
    args=parser.parse_args()
    report={'passed':False,'physical_touch_tested':False,'accepted_values':0,'rejected_values':0}
    with Device(args.port) as device:
        before=read(device)
        report['original']={k:before[k] for k in FIELDS}
        try:
            for field,count in enumerate(COUNTS):
                for value in range(count):
                    reply=device.command(f'@appearance-set {field} {value}','@appearance_set ')
                    assert reply=='@appearance_set ok',reply
                    assert read(device)[FIELDS[field]]==value
                    report['accepted_values']+=1
                for value in (count,4294967295):
                    snapshot=read(device)
                    reply=device.command(f'@appearance-set {field} {value}','@appearance_set ')
                    assert reply=='@appearance_set invalid',reply
                    after=read(device)
                    assert all(after[k]==snapshot[k] for k in FIELDS)
                    report['rejected_values']+=1
            for text in ('4 0','0 -1','0 0 extra','missing','0'):
                reply=device.command('@appearance-set '+text,'@appearance_set ')
                assert reply=='@appearance_set invalid',reply
                report['rejected_values']+=1
            expected=saved(device)
            device.command('@appearance-reload','@appearance_reload ')
            after=read(device)
            assert all(after[k]==expected[k] for k in FIELDS) and after['saved']
            report['nvs_reload']=True
        finally:
            for field,key in enumerate(FIELDS):
                device.command(f'@appearance-set {field} {before[key]}','@appearance_set ')
            restored=saved(device)
            assert all(restored[k]==before[k] for k in FIELDS)
            report['original_restored']=True
            device.port.write(b'@close\n@emote idle\n')
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    if args.reboot:report.update(reboot_check(args.port,before))
    report['passed']=True
    args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report),flush=True)

if __name__=='__main__':main()
