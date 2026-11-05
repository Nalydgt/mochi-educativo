"""Measure repeated cached PCM downloads over the device's actual VPN route.

This does not claim to test microphone capture, speaker playback or 100 spoken
conversations. No speech, credentials or transcript contents enter the report.
"""
import argparse
import json
from pathlib import Path
import re
import time

import serial


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--count',type=int,default=100)
    parser.add_argument('--port',default='COM3')
    parser.add_argument('--output',type=Path,default=Path('.runtime/stress-integral.json'))
    args=parser.parse_args()
    if not 1<=args.count<=1000: raise ValueError('Invalid count')
    connection=serial.Serial(port=None,baudrate=115200,timeout=.1)
    connection.dtr=connection.rts=False;connection.port=args.port
    samples=[];pending=bytearray()
    def command(value,pattern,seconds=35):
        connection.write((value+'\n').encode())
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            pending.extend(connection.read(8192))
            while b'\n' in pending:
                line,_,rest=pending.partition(b'\n');pending[:]=rest
                decoded=line.decode('utf-8','replace')
                if re.search('assert failed|Guru Meditation|Backtrace:',decoded): raise RuntimeError('Device fault during stress test')
                if value=='@server-audio' and '@mochi_server_audio ready=0 busy=1' in decoded:
                    time.sleep(.15)
                    connection.write(b'@server-audio\n')
                    continue
                match=re.search(pattern,decoded)
                if match:return match
        raise TimeoutError('Device did not return the expected diagnostic')
    with connection:
        connection.reset_input_buffer()
        for index in range(args.count):
            started=time.monotonic()
            result=command('@server-audio',r'@mochi_server_audio ready=(\d) http=(\d+) bytes=(\d+) result=(\w+)')
            if result[1]!='1' or result[2]!='200' or result[4]!='ESP_OK':
                raise RuntimeError(f'Audio download failed at iteration {index+1}: ready={result[1]} http={result[2]} bytes={result[3]} result={result[4]}')
            memory=command('@audio',r'@mochi_audio .*internal_free=(\d+) dma_largest=(\d+)')
            samples.append({'iteration':index+1,'seconds':round(time.monotonic()-started,3),
                'bytes':int(result[3]),'internal_free':int(memory[1]),'dma_largest':int(memory[2])})
            if (index+1)%10==0: print('Verified downloads:',index+1,flush=True)
    report={'kind':'cached-pcm-downloads-through-device-vpn','microphone_tested':False,
        'speaker_tested':False,'count':len(samples),'passed':len(samples)==args.count,
        'minimum_internal_free':min(s['internal_free'] for s in samples),
        'minimum_dma_largest':min(s['dma_largest'] for s in samples),'samples':samples}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='samples'}),flush=True)


if __name__=='__main__':main()
