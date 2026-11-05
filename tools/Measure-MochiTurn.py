"""Measure a synthetic end-to-end turn without recording the household.

Uses a separate diagnostic history and prints only timings and byte counts.
"""
import argparse
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError
from urllib.request import Request,urlopen
import wave


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,default=Path('voice-bank/prueba-espanol-03/nas/02-tranquila.wav'))
    parser.add_argument('--output',type=Path,default=Path('.runtime/turn-latency.json'))
    parser.add_argument('--stream',action='store_true')
    parser.add_argument('--uncached',action='store_true',help='Require fresh NAS synthesis, even for repeated text')
    parser.add_argument('--session',default='',help='Separate synthetic diagnostic history (letters, numbers, hyphen)')
    parser.add_argument('--battery',type=int,choices=range(101),metavar='0..100',
                        help='Attach synthetic pet/battery context, as the physical client does')
    args=parser.parse_args()
    if args.session and not re.fullmatch(r'[A-Za-z0-9_-]{1,20}',args.session):raise ValueError('Invalid diagnostic session')
    with wave.open(str(args.input),'rb') as source:
        if (source.getframerate(),source.getsampwidth(),source.getnchannels())!=(16000,2,1) or source.getnframes()>128000:
            raise ValueError('Use a synthetic mono 16 kHz PCM16 clip of at most eight seconds')
        pcm=source.readframes(source.getnframes())
    token=Path('.runtime/mochi-device.key').read_text().strip()
    headers={'Authorization':'Bearer '+token,'Content-Type':'application/octet-stream',
        'X-Device-ID':'mochi-diagnostics'+('-'+args.session if args.session else '')}
    if args.stream: headers['X-Mochi-Stream']='pcm16'
    if args.uncached:headers['X-Mochi-Audio-Cache']='bypass'
    if args.battery is not None:
        headers['X-Mochi-Context']=json.dumps({'name':'Mochi',
            'battery_percent':args.battery,'charging':False,'trigger':'manual'},separators=(',',':'))
    began=time.monotonic(); deadline=began+90
    while True:
        request=Request('http://192.168.8.245:8765/v1/turn',data=pcm,headers=headers)
        started=time.monotonic()
        try:
            with urlopen(request,timeout=180) as response:
                first=response.read(2)
                first_audio=time.monotonic()-started
                print(json.dumps({'first_audio_seconds':round(first_audio,3)}),flush=True)
                body=first+response.read(16000*2*45+1)
                timing=response.headers.get('Server-Timing','')
                progressive=response.headers.get('X-Mochi-Stream')=='pcm16'
                bypassed=response.headers.get('X-Mochi-Audio-Cache')=='bypass'
            break
        except HTTPError as failure:
            if failure.code!=429 or time.monotonic()>deadline:raise
            print('Waiting for the active conversation to finish.',flush=True)
            time.sleep(3)
    if not body or len(body)%2 or len(body)>16000*2*45:raise RuntimeError('Invalid response audio')
    if args.uncached and not bypassed:raise RuntimeError('The server did not confirm fresh synthesis')
    stages={key:float(value) for key,value in re.findall(r'([a-z_]+);dur=([0-9.]+)',timing)}
    report={'synthetic_input':True,'physical_microphone_tested':False,'first_audio_seconds':round(first_audio,3),
        'progressive_pcm':progressive,
        'audio_cache_bypassed':bypassed,
        'synthetic_device_context':args.battery is not None,
        'request_seconds':round(time.monotonic()-started,3),'queue_wait_seconds':round(started-began,3),
        'server_stages_ms':stages,'pcm_bytes':len(body)}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report),flush=True)


if __name__=='__main__':main()
