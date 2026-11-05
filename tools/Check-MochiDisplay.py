"""Exercise real rendering and LCD brightness over USB, preserving preferences.

This verifies firmware/UI transport, not a person's physical touch response.
"""
import argparse
import json
from pathlib import Path
import re
import time

import serial


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',default='COM3')
    parser.add_argument('--output',type=Path,default=Path('.runtime/display-check.json'))
    args=parser.parse_args()
    port=serial.Serial(port=None,baudrate=115200,timeout=.1)
    port.dtr=port.rts=False; port.port=args.port
    pending=bytearray(); frames=[]
    def request(command,pattern):
        port.write((command+'\n').encode())
        deadline=time.monotonic()+12
        while time.monotonic()<deadline:
            pending.extend(port.read(8192))
            while b'\n' in pending:
                line,_,tail=pending.partition(b'\n'); pending[:]=tail
                text=line.decode('utf-8','replace')
                if re.search(r'assert failed|Guru Meditation|Backtrace:',text):
                    raise RuntimeError('Device fault during display check')
                match=re.search(pattern,text)
                if match: return match
        raise TimeoutError('Display check did not finish')
    passed=False; error=None
    with port:
        port.reset_input_buffer()
        try:
            for page in (0,2,3,5,8,9,0):
                port.write(f'@dashboard {page}\n'.encode())
                time.sleep(.3)
                result=request('@display-test',r'@mochi_display_test (PASS|FAIL)')
                if result[1]!='PASS': raise RuntimeError('Panel command failed')
                unlocked=request('@display',r'@mochi_display_ui lock=(\d) awake=(\d)')
                if unlocked[1]!='1': raise RuntimeError('LVGL lock is stuck')
                frame=request('@display',r'@mochi_display submitted=(\d+) completed=(\d+) pending=(\d+) idle_ms=(\d+)')
                count=int(frame[2]); frames.append({'page':page,'completed':count,'idle_ms':int(frame[4])})
                if len(frames)>1 and count<=frames[-2]['completed']:
                    raise RuntimeError('LCD frame counter stopped')
                print('Display page verified:',page,'frames:',count,flush=True)
            passed=True
        except Exception as failure:
            error=type(failure).__name__+': '+str(failure)
        finally:
            port.write(b'@close\n')
            time.sleep(.3)
    report={'kind':'real-lcd-rendering-and-brightness','passed':passed,
        'physical_touch_tested':False,'brightness_changes':len(frames)*12,'frames':frames,'error':error}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({key:value for key,value in report.items() if key!='frames'}))
    if not passed: raise SystemExit(1)


if __name__=='__main__': main()
