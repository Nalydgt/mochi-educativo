"""Small supplementary sample with the installed client's normal cache policy."""
import argparse,json
from pathlib import Path
from nas import NAS
ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--phase',choices=('before','after'),required=True)
    p.add_argument('--settings',type=Path,default=ROOT/'.runtime/nas.json');a=p.parse_args()
    nas=NAS(json.loads(a.settings.read_text()))
    try:
        script='PHASE='+repr(a.phase)+'\n'+'''
from pathlib import Path
import time,json,re
from urllib.request import Request,urlopen
from app import Settings
s=Settings.from_env();root=Path('/data/optimization-20261026');rows=[]
def request(path,data=None,headers=None):
    return urlopen(Request('http://127.0.0.1:8765'+path,data=data,headers={'Authorization':'Bearer '+s.token,**(headers or {})}),timeout=180)
for i in (5,10,4,5):
    with request('/health') as r:before=json.load(r)['audio_cache']['reuses']
    start=time.monotonic()
    with request('/v1/turn',(root/f'input-{i:02d}.pcm').read_bytes(),{'Content-Type':'application/octet-stream',
        'X-Device-ID':'mochi-diagnostics-usual-'+PHASE,'X-Mochi-Stream':'pcm16'}) as response:
        first=response.read(2);first_time=time.monotonic()-start;data=first+response.read(1440001)
        timing=response.headers.get('Server-Timing','');route=response.headers.get('X-Mochi-Route','hermes')
    with request('/health') as r:after=json.load(r)['audio_cache']['reuses']
    rows.append({'input_index':i,'first_pcm_seconds':round(first_time,3),'total_seconds':round(time.monotonic()-start,3),
        'cache_reuses':after-before,'pcm_bytes':len(data),'route':route,
        'stages_ms':{k:float(v) for k,v in re.findall(r'([a-z_]+);dur=([0-9.]+)',timing)}})
print(json.dumps({'phase':PHASE,'audio_cache':'use','synthetic':True,'physical_first_sound_measured':False,'questions':rows}))
'''
        output=nas.container('mochi-voice','mochi',"cd /app\n/data/venv/bin/python -u - <<'PY'\n"+script+'\nPY',timeout=700)
        print(output)
        (ROOT/f'docs/mediciones/20261026-habitual-{a.phase}.json').write_text(output+'\n')
    finally:nas.close()


if __name__=='__main__':main()
