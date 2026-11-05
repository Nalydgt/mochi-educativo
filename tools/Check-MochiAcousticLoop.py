"""Play synthetic speech on the PC into the real board microphone.

Requires the board near the PC speaker. No microphone recording is saved on
the PC. The normal device route sends its temporary capture to the NAS.
"""
import argparse,base64,hashlib,json,re,time,wave
from pathlib import Path
from nas import NAS
from mochi_device import Device,voice_timings
ROOT=Path(__file__).resolve().parents[1]


def main():
    import winsound
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--settings',type=Path,default=ROOT/'.runtime/nas.json')
    p.add_argument('--port',default='COM3')
    p.add_argument('--input',type=Path,help='Replay an existing synthetic mono 16 kHz PCM16 WAV')
    p.add_argument('--output',type=Path,default=ROOT/'.runtime/acoustic-loop-latency.json')
    a=p.parse_args()
    if a.input:
        path=a.input
        with wave.open(str(path),'rb') as wav:
            if (wav.getnchannels(),wav.getsampwidth(),wav.getframerate())!=(1,2,16000) or not 3200<=wav.getnframes()<=128000:
                raise ValueError('Use a synthetic mono 16 kHz PCM16 WAV between 0.2 and 8 seconds')
            pcm=wav.readframes(wav.getnframes())
    else:
        settings=json.loads(a.settings.read_text());nas=NAS(settings)
        try:
            raw=nas.container('mochi-voice','mochi',"cd /app\n/data/venv/bin/python - <<'PY'\n"+'''
import base64
from app import Settings
local=Settings.from_env().local_speech()
print(base64.b64encode(local.speak('¿Cuánto es treinta y siete más ocho?')).decode())
PY''')
            pcm=base64.b64decode(raw)
        finally:nas.close()
        path=ROOT/'.runtime/acoustic-loop-input.wav'
        with wave.open(str(path),'wb') as wav:
            wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(16000);wav.writeframes(pcm)
    with Device(a.port) as d:
        report={'firmware':d.command('@firmware','@mochi_firmware '),'passed':False,'synthetic_pc_input':True,
            'microphone_recording_saved_on_pc':False,'pcm_input_sha256':hashlib.sha256(pcm).hexdigest()}
        d.port.write(b'@close\n');time.sleep(.3)
        d.command('@ui-pointer 233 233 1','@mochi_ui_pointer ')
        try:
            time.sleep(1.1)
            winsound.PlaySound(str(path),winsound.SND_FILENAME)
        finally:d.command('@ui-pointer 233 233 0','@mochi_ui_pointer ')
        start=time.monotonic();samples=0;opened=0
        while time.monotonic()-start<180:
            state=d.command('@mochi-av','@mochi_av ')
            values={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',state)}
            if values.get('active') and values.get('speaking'):
                samples+=1;opened+=int(values.get('pose',0)>0)
            event=next((e for e in d.events if e.startswith('Voice response: ')),None)
            if event:
                result={k:int(v) for k,v in re.findall(r'(\w+)=(-?\d+)',event)}
                assert 'result=ESP_OK' in event and result['http']==200,event
                assert result['played']==result['bytes']>0 and samples and opened
                report.update(passed=True,response=event,**voice_timings(result),
                    active_samples=samples,open_mouth_samples=opened)
                break
            time.sleep(.08)
        else:raise TimeoutError('The PC speaker did not produce a complete real board conversation')
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report),flush=True)


if __name__=='__main__':main()
