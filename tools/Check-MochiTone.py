"""Capture short, synthetic examples for a human review of Mochi's tone."""
import argparse,json
from pathlib import Path
from urllib.request import Request,urlopen
ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--settings',type=Path,default=ROOT/'.runtime/nas.json');a=p.parse_args()
    settings=json.loads(a.settings.read_text());token=(ROOT/settings['device_key_file']).read_text().strip();rows=[]
    for text in ('He terminado un proyecto difícil.','Hoy estoy cansado. Acompáñame un momento.','¿Cuál es la capital de Noruega?'):
        with urlopen(Request('http://'+settings['host']+':8765/v1/chat',
            data=json.dumps({'device_id':'mochi-diagnostics-tone','text':text}).encode(),
            headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'}),timeout=180) as response:
            answer=json.load(response);route=response.headers.get('X-Mochi-Route')
        rows.append({'synthetic_question':text,'answer':answer['text'],'route':route})
    assert 'oslo' in rows[-1]['answer'].lower()
    report={'synthetic':True,'human_review_required':True,'samples':rows}
    (ROOT/'docs/mediciones/20261026-tono.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
