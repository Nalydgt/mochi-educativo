"""Check live recall across direct Qwen and Hermes using a synthetic namespace."""
import argparse,json,time
from pathlib import Path
from urllib.request import Request,urlopen
from nas import NAS
ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--settings',type=Path,default=ROOT/'.runtime/nas.json');a=p.parse_args()
    settings=json.loads(a.settings.read_text());token=(ROOT/settings['device_key_file']).read_text().strip()
    base='http://'+settings['host']+':8765';device='mochi-diagnostics-shared-'+str(int(time.time()))
    report={'synthetic':True,'personal_memories_changed':False,'checks':[]}
    for text,required_route,expected in (
        ('Mi color de prueba es turquesa.','fast',None),
        ('¿Cuál es mi color de prueba?','fast','turquesa'),
        ('Usa mochi_history_search para consultar cuál era mi color de prueba en el registro local. No guardes nada en MEMORY ni USER.','hermes','turquesa')):
        start=time.monotonic()
        with urlopen(Request(base+'/v1/chat',data=json.dumps({'text':text,'device_id':device}).encode(),
            headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'}),timeout=180) as r:
            answer=json.load(r);route=r.headers.get('X-Mochi-Route')
        assert route==required_route,(route,required_route)
        assert not expected or expected in answer['text'].lower(),answer
        report['checks'].append({'route':route,'recall_correct':True if expected else None,'seconds':round(time.monotonic()-start,3)})
    nas=NAS(settings)
    try:
        raw=nas.container('mochi-voice','mochi',"cd /app\n/data/gateway-runtime/venv/bin/python - <<'PY'\n"+'DEVICE='+repr(device)+'\n'+'''
from app import Settings
from memory_store import Memory
store=Memory(Settings.from_env().memory_path)
with store.connect() as db:
    count=db.execute('SELECT count(*) FROM exchanges WHERE device=?',(DEVICE,)).fetchone()[0]
    print(count)
PY''')
        assert int(raw)==3,'Hermes sync duplicated gateway exchanges'
        report.update(passed=True,duplicate_exchanges=0)
    finally:nas.close()
    (ROOT/'docs/mediciones/20261026-memoria-entre-rutas.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report),flush=True)


if __name__=='__main__':main()
