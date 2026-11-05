"""Install the frozen synthetic input corpus; never uses household recordings."""
import argparse,hashlib,json
from pathlib import Path
from nas import NAS
ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--settings',type=Path,default=ROOT/'.runtime/nas.json');a=p.parse_args()
    settings=json.loads(a.settings.read_text());nas=NAS(settings)
    try:
        directory=settings['gateway_remote']+'/benchmark-inputs'
        nas.python('from pathlib import Path\nPath('+repr(directory)+').mkdir(exist_ok=True,mode=0o700)')
        manifest=json.loads((ROOT/'tests/fixtures/synthetic/manifest.json').read_text())
        for item in manifest['inputs']:
            path=ROOT/'tests/fixtures/synthetic'/item['file']
            if hashlib.sha256(path.read_bytes()).hexdigest()!=item['wav_sha256']:raise ValueError('Synthetic fixture changed')
            nas.upload(path,directory+'/'+item['file'])
        script='MANIFEST='+repr(manifest)+'\n'+'''
import wave,hashlib,json
from pathlib import Path
root=Path('/data/optimization-20261026');root.mkdir(exist_ok=True,mode=0o700)
for item in MANIFEST['inputs']:
    with wave.open('/app/benchmark-inputs/'+item['file'],'rb') as wav:
        assert (wav.getframerate(),wav.getsampwidth(),wav.getnchannels())==(16000,2,1)
        pcm=wav.readframes(wav.getnframes())
    assert hashlib.sha256(pcm).hexdigest()==item['pcm_sha256']
    target=root/('input-%02d.pcm'%item['index'])
    if target.exists() and target.read_bytes()!=pcm:raise ValueError('Existing diagnostic input differs; preserve its measurement set')
    target.write_bytes(pcm)
print(json.dumps({'synthetic_inputs_verified':len(MANIFEST['inputs'])}))
'''
        print(nas.container('mochi-voice','mochi',"python - <<'PY'\n"+script+'\nPY'))
    finally:nas.close()


if __name__=='__main__':main()
