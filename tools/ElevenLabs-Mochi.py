"""Clone Mochi's existing synthetic voice and measure uncached ElevenLabs PCM.

Private keys, source recordings, clone metadata and generated WAVs stay under
.runtime. A repeated clone command reuses its saved voice instead of cloning again.
"""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import statistics
import sys
import time
import wave

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'gateway'))
from elevenlabs_voice import ElevenLabsVoice


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix+'.partial')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    temporary.replace(path)


def samples(paths):
    result = []
    hashes = set()
    for path in paths:
        content = path.read_bytes()
        digest = sha256(content).hexdigest()
        if digest in hashes:
            continue
        with wave.open(str(path), 'rb') as source:
            if (source.getnchannels(), source.getsampwidth(), source.getcomptype()) != (1, 2, 'NONE'):
                raise ValueError('Expected clean mono PCM16 source WAVs')
            seconds = source.getnframes()/source.getframerate()
            if not 1 <= seconds <= 180:
                raise ValueError('Invalid clone sample duration')
        hashes.add(digest)
        result.append({'path': str(path.resolve()), 'sha256': digest, 'seconds': seconds})
    if not result or sum(x['seconds'] for x in result) < 10:
        raise ValueError('At least ten seconds of the existing speaker is required')
    return result


def clone(client, paths, output, name):
    manifest = samples(paths)
    revision = sha256(json.dumps([{'sha256':x['sha256'], 'seconds':x['seconds']} for x in manifest],
                                sort_keys=True).encode()).hexdigest()
    if output.exists():
        previous = json.loads(output.read_text(encoding='utf-8'))
        if previous.get('source_revision') != revision:
            raise ValueError('Source changed; use a new metadata output to create a different clone')
        if previous.get('voice_id'):
            print(json.dumps({'voice_id':previous['voice_id'], 'reused':True}), flush=True)
            return previous
    # Reconcile an ambiguous earlier POST by its source revision; never blindly retry.
    voices = client.get('/v1/voices')
    voices.raise_for_status()
    matches = [v for v in voices.json().get('voices', [])
               if v.get('name') == name and revision in v.get('description', '')]
    if len(matches) > 1:
        raise ValueError('Multiple matching clones; select the intended voice in ElevenLabs')
    started = time.perf_counter()
    if matches:
        data = {'voice_id':matches[0]['voice_id'], 'requires_verification':False}
    else:
        files = [('files', (Path(x['path']).name, Path(x['path']).read_bytes(), 'audio/wav')) for x in manifest]
        response = client.post('/v1/voices/add', data={'name':name,
            'description':'Existing synthetic Mochi voice 03. Source revision '+revision,
            'labels':json.dumps({'language':'es', 'gender':'female'}),
            'remove_background_noise':'false'}, files=files, timeout=120)
        response.raise_for_status()
        data = response.json()
    # Validate the returned identifier before persisting it into URLs/configuration.
    import re
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', data.get('voice_id', '')):
        raise ValueError('Unexpected clone response')
    result = {'created_utc':datetime.now(timezone.utc).isoformat(), 'name':name,
        'voice_id':data['voice_id'], 'requires_verification':data.get('requires_verification', False),
        'source_revision':revision, 'source_samples':manifest,
        'source_seconds':sum(x['seconds'] for x in manifest),
        'recommended_minute_available':sum(x['seconds'] for x in manifest) >= 60,
        'clone_seconds':time.perf_counter()-started, 'model_id':'eleven_flash_v2_5'}
    save(output, result)
    print(json.dumps({k:v for k,v in result.items() if k != 'source_samples'}), flush=True)
    if result['requires_verification']:
        raise ValueError('ElevenLabs requires account verification before synthesis; clone metadata saved')
    return result


def measure(key, metadata, output, repeats, model):
    texts = ['Estoy aquí.', 'Puedo ayudarte con eso.',
        'Hola, soy Mochi. ¿Qué tal estás?',
        'La respuesta es sencilla: podemos empezar por revisar lo que necesitas ahora mismo.']
    report = {'started_utc':datetime.now(timezone.utc).isoformat(),
        'voice_id':metadata['voice_id'], 'source_revision':metadata['source_revision'],
        'model_id':model, 'location':'development_pc', 'nas_measured':False,
        'device_measured':False, 'physical_sound_measured':False, 'cache':'bypass',
        'measurements':[], 'all_valid':False}
    selected = ElevenLabsVoice(key, metadata['voice_id'], model, revision=metadata['source_revision'])
    try:
        for repeat in range(repeats):
            for index, text in enumerate(texts):
                pcm, timing = selected.generate_measured(text)
                filename = f'{repeat:02d}-{index:02d}.wav'
                output.mkdir(parents=True, exist_ok=True)
                with wave.open(str(output/filename), 'wb') as destination:
                    destination.setnchannels(1); destination.setsampwidth(2); destination.setframerate(16000)
                    destination.writeframes(pcm)
                row = {'repeat':repeat, 'text':text, 'characters':len(text), 'file':filename,
                    'pcm_sha256':sha256(pcm).hexdigest(), **timing}
                report['measurements'].append(row)
                save(output/'report.json', report)
                print(json.dumps(row, ensure_ascii=False), flush=True)
        report.update(all_valid=True,
            median_first_pcm_seconds=statistics.median(x['first_pcm_seconds'] for x in report['measurements']),
            median_phrase_seconds=statistics.median(x['phrase_seconds'] for x in report['measurements']),
            max_phrase_seconds=max(x['phrase_seconds'] for x in report['measurements']))
        save(output/'report.json', report)
        print(json.dumps({k:v for k,v in report.items() if k != 'measurements'}), flush=True)
    finally:
        selected.close()
    return report


def measure_nas(key_file, metadata, settings_file, output, repeats, model):
    """Measure the real NAS connection without installing host packages."""
    from nas import NAS
    settings = json.loads(settings_file.read_text(encoding='utf-8'))
    nas = NAS(settings)
    remote = '/home/'+settings['user']+'/mochi-elevenlabs-staging'
    try:
        nas.python('from pathlib import Path\np=Path('+repr(remote)+')\n'
                   'p.mkdir(mode=0o700,exist_ok=True)\np.chmod(0o700)')
        nas.upload(key_file, remote+'/api.key')
        with nas.client.open_sftp() as sftp:
            sftp.chmod(remote+'/api.key', 0o600)
        parameters = {'voice_id':metadata['voice_id'], 'source_revision':metadata['source_revision'],
            'model_id':model, 'repeats':repeats, 'remote':remote}
        source = 'CONFIG='+repr(parameters)+'\n'+'''
from datetime import datetime,timezone
from pathlib import Path
import json,statistics,time,wave
from urllib.request import Request,urlopen
from urllib.error import HTTPError
root=Path(CONFIG['remote']);key=(root/'api.key').read_text().strip()
report={'started_utc':datetime.now(timezone.utc).isoformat(),'location':'nas',
 'nas_measured':True,'device_measured':False,'physical_sound_measured':False,
 'cache':'bypass','voice_id':CONFIG['voice_id'],'model_id':CONFIG['model_id'],
 'source_revision':CONFIG['source_revision'],'measurements':[],'all_valid':False}
texts=['Estoy aquí.','Puedo ayudarte con eso.','Hola, soy Mochi. ¿Qué tal estás?',
 'La respuesta es sencilla: podemos empezar por revisar lo que necesitas ahora mismo.']
for repeat in range(CONFIG['repeats']):
 for index,text in enumerate(texts):
  payload={'text':text,'model_id':CONFIG['model_id'],'language_code':'es',
   'voice_settings':{'stability':.65,'similarity_boost':.85,'style':0,'use_speaker_boost':False,'speed':1.0}}
  request=Request('https://api.elevenlabs.io/v1/text-to-speech/'+CONFIG['voice_id']+'/stream?output_format=pcm_16000',
   data=json.dumps(payload).encode(),headers={'xi-api-key':key,'Content-Type':'application/json'})
  started=time.perf_counter();first=None;pcm=bytearray()
  try:
   with urlopen(request,timeout=30) as response:
    if response.headers.get_content_type() not in ('application/octet-stream','audio/pcm','audio/x-pcm'):
     raise ValueError('Unexpected PCM content type')
    while True:
     chunk=response.read1(65536)
     if not chunk:break
     if first is None:first=time.perf_counter()-started
     pcm.extend(chunk)
     if len(pcm)>1440000:raise ValueError('Oversized PCM')
  except HTTPError as e:raise RuntimeError('ElevenLabs HTTP '+str(e.code)) from None
  elapsed=time.perf_counter()-started
  if not pcm or len(pcm)%2:raise ValueError('Invalid PCM')
  filename='nas-%02d-%02d.wav'%(repeat,index)
  with wave.open(str(root/filename),'wb') as w:
   w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(pcm)
  report['measurements'].append({'repeat':repeat,'text':text,'characters':len(text),
   'first_pcm_seconds':first,'phrase_seconds':elapsed,'pcm_bytes':len(pcm),
   'audio_seconds':len(pcm)/32000,'file':filename})
report.update(all_valid=True,
 median_first_pcm_seconds=statistics.median(x['first_pcm_seconds'] for x in report['measurements']),
 median_phrase_seconds=statistics.median(x['phrase_seconds'] for x in report['measurements']),
 max_phrase_seconds=max(x['phrase_seconds'] for x in report['measurements']))
(root/'nas-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=True),flush=True)
'''
        report = json.loads(nas.python(source, timeout=180))
        save(output, report)
        print(json.dumps({k:v for k,v in report.items() if k != 'measurements'}), flush=True)
        return report
    finally:
        nas.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--key-file', type=Path, default=ROOT/'.runtime/elevenlabs-api.key')
    parser.add_argument('--metadata', type=Path, default=ROOT/'.runtime/elevenlabs-voice03.json')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('account')
    create = commands.add_parser('clone')
    create.add_argument('--sample', type=Path, action='append', required=True)
    create.add_argument('--name', default='Mochi voz 03')
    benchmark = commands.add_parser('measure')
    benchmark.add_argument('--output', type=Path, required=True)
    benchmark.add_argument('--repeats', type=int, choices=range(1, 6), default=3)
    benchmark.add_argument('--model', default='eleven_flash_v2_5')
    nas_benchmark = commands.add_parser('measure-nas')
    nas_benchmark.add_argument('--settings', type=Path, default=ROOT/'.runtime/nas.json')
    nas_benchmark.add_argument('--output', type=Path, required=True)
    nas_benchmark.add_argument('--repeats', type=int, choices=range(1, 6), default=3)
    nas_benchmark.add_argument('--model', default='eleven_flash_v2_5')
    args = parser.parse_args()
    key = args.key_file.read_text(encoding='utf-8').strip()
    if args.command in {'measure', 'measure-nas'}:
        metadata = json.loads(args.metadata.read_text(encoding='utf-8'))
        if metadata.get('requires_verification'):
            raise ValueError('Complete ElevenLabs voice verification before measuring')
        if args.command == 'measure-nas':
            measure_nas(args.key_file, metadata, args.settings, args.output, args.repeats, args.model)
        else:
            measure(key, metadata, args.output, args.repeats, args.model)
    else:
        with httpx.Client(base_url='https://api.elevenlabs.io', headers={'xi-api-key':key},
                          follow_redirects=False, timeout=15) as client:
            if args.command == 'clone':
                clone(client, args.sample, args.metadata, args.name)
            else:
                response = client.get('/v1/user/subscription'); response.raise_for_status()
                data = response.json()
                print(json.dumps({k:data.get(k) for k in ('tier', 'character_count', 'character_limit',
                    'can_use_instant_voice_cloning')}))


if __name__ == '__main__':
    try:
        main()
    except httpx.HTTPStatusError as exc:
        # Provider errors can contain private text. Do not print bodies or headers.
        raise SystemExit('ElevenLabs returned HTTP '+str(exc.response.status_code)) from None
