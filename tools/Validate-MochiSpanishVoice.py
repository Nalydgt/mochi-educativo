"""Check the real NAS speaker and save the five requested synthetic test clips."""
import hashlib
import argparse
import json
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.request import Request,urlopen
import wave

ROOT=Path(__file__).resolve().parents[1]
BASE='http://192.168.8.245:8767'
PHRASES=(
 ('01-saludo','Hola, soy Mochi. ¿Qué tal estás? Me alegra estar contigo.'),
 ('02-tranquila','Estoy tranquila y tengo ganas de pasar un rato contigo.'),
 ('03-alegria','¡Qué bien! ¡Vamos a jugar juntos!'),
 ('04-pregunta','¿Me llevas a dar un paseo esta tarde?'),
 ('05-numeros','Hoy tengo 80 de energía y he dado 300 pasos.'),
)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default=BASE)
    parser.add_argument('--output',type=Path,default=ROOT/'voice-bank/prueba-espanol-03/nas')
    args=parser.parse_args();base=args.url.rstrip('/')
    identifier=json.loads((ROOT/'.runtime/native-voice-profile.json').read_text(encoding='utf-8'))['profile_id']
    token=(ROOT/'.runtime/mochi-native-voice.key').read_text().strip()
    headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'}
    try:
        urlopen(base+'/health',timeout=5)
        raise RuntimeError('Native voice must require authentication')
    except HTTPError as failure:
        if failure.code!=401:raise
    with urlopen(Request(base+'/health',headers=headers),timeout=5) as response: health=json.load(response)
    if not health.get('ready') or health.get('profile')!=identifier:raise RuntimeError('Chosen voice is not ready')
    output=args.output;output.mkdir(parents=True,exist_ok=True)
    samples=[]
    for name,text in PHRASES:
        started=time.monotonic()
        data=json.dumps({'text':text,'profile':identifier},ensure_ascii=False).encode()
        with urlopen(Request(base+'/v1/speech',data=data,headers=headers),timeout=180) as response:
            if response.headers.get('X-Mochi-Voice-Profile')!=identifier or response.headers.get('X-Mochi-Sample-Rate')!='16000':
                raise RuntimeError('Speaker or audio format changed')
            pcm=response.read(16000*2*45+1)
        if not pcm or len(pcm)%2 or len(pcm)>16000*2*45:raise RuntimeError('Invalid native PCM')
        if name=='01-saludo':
            with wave.open(str(ROOT/'voice-bank/prueba-espanol-03/01-saludo.wav'),'rb') as source:
                if pcm!=source.readframes(source.getnframes()):raise RuntimeError('Approved greeting changed')
        destination=output/(name+'.wav')
        with wave.open(str(destination),'wb') as wav:
            wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(16000);wav.writeframes(pcm)
        item={'file':destination.name,'seconds':round(len(pcm)/32000,3),
            'request_seconds':round(time.monotonic()-started,3),'sha256':hashlib.sha256(destination.read_bytes()).hexdigest()}
        samples.append(item);print(json.dumps(item),flush=True)
    report={'profile':identifier,'host':'local GPU' if health.get('device')=='cuda' else 'NAS CPU, four threads','passed_format_and_identity':True,
        'speaker_on_device_tested':False,'approved_greeting_identical':True,'samples':samples}
    (output/'validacion.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
