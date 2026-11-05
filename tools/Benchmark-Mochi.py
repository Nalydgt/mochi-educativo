"""Repeat the same 20 synthetic recordings on the NAS and compare first PCM.

This measures HTTP audio readiness, not acoustic first sound. Private audio and
personal journals never leave the NAS. Only synthetic questions/results export.
"""
import argparse
import json
import math
from pathlib import Path
import statistics

from nas import NAS

ROOT=Path(__file__).resolve().parents[1]


def compare(before,after):
    def indexed(run):
        rows={}
        for row in run['questions']:
            index=row['index']
            if type(index) is not int or not 0<=index<20 or index in rows:
                raise ValueError('Expected distinct question indices from 0 to 19')
            rows[index]=row
        return rows
    def successful(row):
        latency=row.get('first_pcm_seconds')
        size=row.get('pcm_bytes',0)
        return (row.get('status')==200 and isinstance(latency,(int,float))
            and math.isfinite(latency) and latency>0 and type(size) is int
            and 2<=size<=1440000 and size%2==0)
    old_rows,new_rows=indexed(before),indexed(after)
    pairs=[(old_rows[index],new_rows[index]) for index in sorted(old_rows.keys() & new_rows.keys())
        if successful(old_rows[index]) and successful(new_rows[index])
        and old_rows[index].get('question')==new_rows[index].get('question')
        # Historical baseline reports predate input hashes. Compare hashes
        # whenever both runs recorded them, retaining those older reports.
        and (not old_rows[index].get('pcm_input_sha256') or not new_rows[index].get('pcm_input_sha256')
            or old_rows[index]['pcm_input_sha256']==new_rows[index]['pcm_input_sha256'])]
    def percentile(values,p):
        ordered=sorted(values);position=(len(ordered)-1)*p;lower=int(position)
        return ordered[lower]+(ordered[min(lower+1,len(ordered)-1)]-ordered[lower])*(position-lower)
    # First question has a cold context/model; compare it separately. Median
    # acceptance is based on the remaining distinct, uncached questions.
    warm=[(a,b) for a,b in pairs if a['index']!=0]
    old=[a['first_pcm_seconds'] for a,b in warm];new=[b['first_pcm_seconds'] for a,b in warm]
    if not old or not new:raise ValueError('No comparable successful measurements')
    cold=next(((a,b) for a,b in pairs if a['index']==0),None)
    reduction=1-statistics.median(new)/statistics.median(old)
    return {'accepted':len(pairs)==20 and reduction>=.30 and percentile(new,.95)<percentile(old,.95),
        'paired_questions':len(pairs),'warm_median_before_seconds':statistics.median(old),
        'warm_median_after_seconds':statistics.median(new),'median_reduction_percent':round(reduction*100,2),
        'warm_p95_before_seconds':percentile(old,.95),'warm_p95_after_seconds':percentile(new,.95),
        'percentile_method':'linear_type_7','warm_max_before_seconds':max(old),'warm_max_after_seconds':max(new),
        'first_question_before_seconds':cold[0]['first_pcm_seconds'] if cold else None,
        'first_question_after_seconds':cold[1]['first_pcm_seconds'] if cold else None,
        'physical_first_sound_measured':False,'audio_cache':'bypass','before':before,'after':after}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--settings',type=Path,default=ROOT/'.runtime/nas.json')
    p.add_argument('--url',default=None)
    p.add_argument('--output',type=Path,default=ROOT/'docs/mediciones/20261026-voz-comparacion.json')
    p.add_argument('--fetch-only',action='store_true')
    p.add_argument('--baseline',action='store_true',help='Capture a new reference run, archiving any previous reference on the NAS')
    a=p.parse_args();nas=NAS(json.loads(a.settings.read_text()))
    try:
        if not a.fetch_only:
            corpus=json.loads((ROOT/'tests/fixtures/synthetic/manifest.json').read_text(encoding='utf-8'))['inputs']
            phase='before' if a.baseline else 'after'
            script='URL='+repr(a.url or ('http://192.168.8.245:8765' if a.baseline else 'http://192.168.8.245:8777'))+'\nPHASE='+repr(phase)+'\nCORPUS='+repr(corpus)+'\n'+'''
import json,time,re,sqlite3,hashlib,shutil
from pathlib import Path
from urllib.request import Request,urlopen
from app import Settings
s=Settings.from_env();root=Path('/data/optimization-20261026')
device='mochi-diagnostics-'+PHASE+'-'+str(int(time.time()))
target=root/(PHASE+'.json')
if target.exists():shutil.copy2(target,root/(PHASE+'-'+str(int(time.time()))+'.json'))
rows=[]
for item in CORPUS:
    i=item['index'];pcm=(root/f'input-{i:02d}.pcm').read_bytes()
    start=time.monotonic()
    try:
        with urlopen(Request(URL+'/v1/turn',data=pcm,headers={'Authorization':'Bearer '+s.token,'Content-Type':'application/octet-stream',
            'X-Device-ID':device,'X-Mochi-Stream':'pcm16','X-Mochi-Audio-Cache':'bypass'}),timeout=180) as response:
            first=response.read(2);elapsed=time.monotonic()-start;data=first+response.read(1440001)
            row={'index':i,'question':item['question'],'condition':'cold_context' if i==0 else 'uncached_new_question','status':response.status,
                'first_pcm_seconds':round(elapsed,3),'total_seconds':round(time.monotonic()-start,3),'pcm_bytes':len(data),
                'brain_route':response.headers.get('X-Mochi-Route'),'exchange_id':response.headers.get('X-Mochi-Turn-ID'),
                'pcm_input_sha256':hashlib.sha256(pcm).hexdigest(),
                'stages_ms':{k:float(v) for k,v in re.findall(r'([a-z_]+);dur=([0-9.]+)',response.headers.get('Server-Timing',''))}}
    except Exception as e:row={'index':i,'question':item['question'],'error':type(e).__name__}
    rows.append(row);target.write_text(json.dumps({'synthetic':True,'physical_first_sound_measured':False,'audio_cache':'bypass','questions':rows},ensure_ascii=False,indent=2))
    print(json.dumps({'index':i,'seconds':row.get('first_pcm_seconds'),'error':row.get('error')}),flush=True)
'''
            print(nas.container('mochi-voice','mochi',"cd /app\n/data/venv/bin/python -u - <<'PY'\n"+script+'\nPY',timeout=2400),flush=True)
            if a.baseline:
                print('Reference run recorded on the NAS; previous reference retained.',flush=True)
                return
        # Only synthetic timing reports cross the boundary.
        code="/data/venv/bin/python - <<'PY'\nfrom pathlib import Path\nimport json\nr=Path('/data/optimization-20261026')\nprint(json.dumps({n:json.loads((r/(n+'.json')).read_text()) for n in ('before','after')}))\nPY"
        data=json.loads(nas.container('mochi-voice','mochi',code))
        report=compare(data['before'],data['after'])
        report['input_manifest']='tests/fixtures/synthetic/manifest.json'
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({k:v for k,v in report.items() if k not in ('before','after')},ensure_ascii=False),flush=True)
    finally:nas.close()


if __name__=='__main__':main()
