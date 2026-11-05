"""Private TrueNAS pilot: prepare, stage, initialize, forward, inspect.

Uses the existing verified SSH identity. Only creates/updates peluqo-pilot.
Never rewrites the original Mochi applications or the hosted Lovable project.
"""
from __future__ import annotations
import argparse,base64,hashlib,hmac,json,os,secrets,shlex,sys,tarfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
MOCHI=ROOT.parent
sys.path.insert(0,str(MOCHI/'tools'))
from nas import NAS
APP='peluqo-pilot'
REMOTE='/home/truenas_admin/peluqo-pilot'
PRIVATE=ROOT/'.runtime'
WORKER_START='if [ ! -x /runtime/venv/bin/python ]; then python -m venv /runtime/venv || exit 1; fi; if ! cmp -s /app/requirements.txt /runtime/requirements.lock; then /runtime/venv/bin/pip install --disable-pip-version-check -r /app/requirements.txt && cp /app/requirements.txt /runtime/requirements.lock || exit 1; fi; exec /runtime/venv/bin/python -m uvicorn app:app --host 0.0.0.0 --port 8000 --no-access-log'

def configure_worker(cfg):
    worker=cfg['services']['worker']
    worker['entrypoint']=['sh','-c',WORKER_START]
    worker['environment']['PYTHONTZPATH']=''
    queue=PRIVATE/'inference-worker.json'
    if queue.exists():
        worker['environment']['PELUQO_QUEUE_DSN']=json.loads(queue.read_text())['url']
        worker['environment']['PELUQO_WEB_URL']='https://peluqo-mundos.vercel.app'

def jwt(key,role):
    encode=lambda v:base64.urlsafe_b64encode(json.dumps(v,separators=(',',':')).encode()).rstrip(b'=').decode()
    body=encode({'alg':'HS256','typ':'JWT'})+'.'+encode({'role':role,'iss':'supabase','iat':int(time.time()),'exp':int(time.time())+31536000})
    return body+'.'+base64.urlsafe_b64encode(hmac.new(key.encode(),body.encode(),hashlib.sha256).digest()).rstrip(b'=').decode()

def credentials():
    PRIVATE.mkdir(exist_ok=True)
    file=PRIVATE/'pilot-secrets.json'
    if file.exists():
        s=json.loads(file.read_text())
        if not s['adult_pin'].isdigit():
            s['adult_pin']=str(100000+secrets.randbelow(900000));file.write_text(json.dumps(s,indent=2))
        return s
    s={k:secrets.token_hex(32) for k in ['database','jwt','integration','pairing','provision','teacher_password','other_password','adult_pin']}
    s['anon']=jwt(s['jwt'],'anon');s['service']=jwt(s['jwt'],'service_role')
    file.write_text(json.dumps(s,indent=2));return s

def settings():return json.loads((MOCHI/'.runtime/nas.json').read_text(encoding='utf-8-sig'))

def prepare(s):
    public=json.loads((PRIVATE/'cloud-public.json').read_text())
    database=json.loads((PRIVATE/'cloud-database.json').read_text())
    env={'VITE_SUPABASE_URL':public['url'],'VITE_SUPABASE_PUBLISHABLE_KEY':public['key'],'VITE_SUPABASE_PROJECT_ID':public['project'],'SUPABASE_URL':public['url'],'SUPABASE_PUBLISHABLE_KEY':public['key'],'PELUQO_DATABASE_URL':database['url'],'PELUQO_AI_URL':'http://localhost:54321','PELUQO_INTEGRATION_KEY':s['integration'],'PELUQO_PAIRING_KEY':s['pairing'],'PELUQO_WEB_ORIGIN':'http://localhost:3000'}
    (ROOT/'.env.pilot.local').write_text('\n'.join(k+'='+v for k,v in env.items())+'\n')
    (PRIVATE/'ACCESO_LOCAL.txt').write_text('PELUQO: acceso exclusivamente de desarrollo\nWeb: http://localhost:3000/expedicion\nDocente: docente@peluqo.local\nContraseña: '+s['teacher_password']+'\nSegundo docente de pruebas: otro@peluqo.local\nContraseña: '+s['other_password']+'\n',encoding='utf-8')
    print(json.dumps({'prepared':True,'credentials_file':str(PRIVATE/'ACCESO_LOCAL.txt')}))

def compose(s,original,vpn_id,revision):
    code=REMOTE+'/revisions/'+revision
    env=original['environment']
    public=json.loads((PRIVATE/'cloud-public.json').read_text())
    database=json.loads((PRIVATE/'cloud-database.json').read_text())
    key_path=next(v.split(':')[0] for v in original['volumes'] if '/run/secrets/elevenlabs-api.key' in v)
    worker_env={'PELUQO_INTEGRATION_KEY':s['integration'],'PELUQO_PROVISION_KEY':s['provision'],'PELUQO_WEB_URL':'http://web:3000','PELUQO_HERMES_URL':env['HERMES_URL'].rstrip('/')+'/p/peluqo/v1','PELUQO_HERMES_KEY':s['hermes'],'PELUQO_ELEVENLABS_VOICE_ID':env['ELEVENLABS_VOICE_ID'],'PELUQO_ELEVENLABS_MODEL':env.get('ELEVENLABS_MODEL_ID','eleven_flash_v2_5'),'PELUQO_ELEVENLABS_KEY_FILE':'/run/secrets/elevenlabs-api.key','PELUQO_ASR_MODEL':'small','HF_HUB_OFFLINE':'0','OMP_NUM_THREADS':'2','PYTHONDONTWRITEBYTECODE':'1'}
    common={'restart':'unless-stopped'}
    return {'services':{
      'web':{**common,'image':'node:22.14.0-bookworm-slim','mem_limit':'640m','working_dir':'/app','entrypoint':['node','/app/server/index.mjs'],'volumes':[code+'/web:/app:ro'],'environment':{'NITRO_HOST':'0.0.0.0','NITRO_PORT':'3000','NODE_ENV':'production','SUPABASE_URL':public['url'],'SUPABASE_PUBLISHABLE_KEY':public['key'],'PELUQO_DATABASE_URL':database['url'],'PELUQO_AI_URL':'http://worker:8000','PELUQO_INTEGRATION_KEY':s['integration'],'PELUQO_PAIRING_KEY':s['pairing'],'PELUQO_WEB_ORIGIN':'http://localhost:3000'},'ports':['127.0.0.1:3010:3000']},
      'worker':{**common,'image':'python:3.11-slim','mem_limit':'1400m','cpus':2,'working_dir':'/app','entrypoint':['sh','-c','if [ ! -f /runtime/ready ]; then python -m venv /runtime/venv && /runtime/venv/bin/pip install --disable-pip-version-check -r /app/requirements.txt && touch /runtime/ready; fi; exec /runtime/venv/bin/python -m uvicorn app:app --host 0.0.0.0 --port 8000 --no-access-log'],'volumes':[code+'/worker:/app:ro','worker-runtime:/runtime','models:/models',key_path+':/run/secrets/elevenlabs-api.key:ro'],'environment':worker_env,'ports':['127.0.0.1:54321:8000'],'networks':{'default':{},'mochi_private':{'aliases':['peluqo-worker']}}},
      'relay':{**common,'image':'python:3.11-slim','mem_limit':'64m','entrypoint':['python','/relay.py'],'volumes':[code+'/worker/relay.py:/relay.py:ro'],'network_mode':'container:'+vpn_id,'environment':{'TARGET_HOST':'peluqo-worker'}},
    },'volumes':{k:{} for k in ['database-v2','storage','worker-runtime','models']},'networks':{'default':{},'mochi_private':{'external':True,'name':'ix-mochi-voice_default'}}}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','stage','inspect','forward']);parser.add_argument('--ai-only',action='store_true');parser.add_argument('--component',choices=['web','worker']);args=parser.parse_args()
    if args.component and args.action!='stage':parser.error('--component requires stage')
    s=credentials()
    if args.action=='prepare':return prepare(s)
    config=settings();n=NAS(config)
    try:
      if args.action=='inspect':
        out=n.python("from truenas_api_client import Client\nimport json\nwith Client() as c:\n print(json.dumps({'apps':[{'id':x['id'],'state':x['state']} for x in c.call('app.query') if x['id']=='peluqo-pilot'],'jobs':[{'method':j['method'],'state':j['state'],'error':j.get('error')} for j in c.call('core.get_jobs') if j['method'] in ('app.create','app.update','app.start')][-5:]}))")
        for value in s.values():out=out.replace(value,'[private]')
        print(out);return
      if args.action=='forward':
        # Explicit local-only SSH forwards; process stays alive until Ctrl+C.
        from pilot_forward import serve
        serve(n.client.get_transport(),web=not args.ai_only);return
      if args.action=='stage':
        if args.component!='worker' and not (ROOT/'.output/server/index.mjs').exists():raise RuntimeError('Build the pilot first')
        original=n.config('mochi-voice');original=original.get('custom_compose_config',original)
        if isinstance(original,str):import yaml;original=yaml.safe_load(original)
        baseline=hashlib.sha256(json.dumps(original,sort_keys=True).encode()).hexdigest()
        preflight=json.loads(n.python("import json,shutil\nfrom truenas_api_client import Client\nwith Client() as c:\n pools=c.call('pool.query')\n print(json.dumps({'memory':int(open('/proc/meminfo').read().split('MemAvailable:')[1].split()[0]),'pools':{p['name']:p['status'] for p in pools},'free':shutil.disk_usage('/home/truenas_admin').free}))"))
        exists=json.loads(n.python("from truenas_api_client import Client\nimport json\nwith Client() as c: print(json.dumps(bool(c.call('app.query',[['id','=','peluqo-pilot']]))))"))
        if args.component and not exists:raise RuntimeError('Deploy the complete pilot before updating a single service')
        memory_floor=900000 if args.component else (1800000 if exists else 4000000)
        if preflight['memory']<memory_floor or preflight['free']<10*1024**3 or preflight['pools'].get('Prueba1')!='ONLINE':raise RuntimeError('NAS preflight does not meet isolated staging requirements')
        archive=PRIVATE/'peluqo-code.tar.gz'
        sources=[(ROOT/'.output','web'),(MOCHI/'services/peluqo_education','worker'),(ROOT/'deploy/education.sql','education.sql')]
        with tarfile.open(archive,'w:gz') as tar:
          for source,target in sources:
            if args.component and args.component!=target:continue
            if source.is_file():tar.add(source,arcname=target)
            else:
              for f in source.rglob('*'):
                if f.is_file() and not any(p in {'__pycache__','.env','data'} for p in f.relative_to(source).parts):tar.add(f,arcname=target+'/'+f.relative_to(source).as_posix())
        revision=hashlib.sha256(archive.read_bytes()).hexdigest()[:16]
        n.python('from pathlib import Path\np=Path('+repr(REMOTE)+')\np.mkdir(mode=0o700,exist_ok=True)\n(p/"revisions").mkdir(exist_ok=True)')
        n.upload(archive,REMOTE+'/code.tar.gz')
        n.python('import tarfile\nfrom pathlib import Path\np=Path('+repr(REMOTE+'/revisions/'+revision)+')\np.mkdir(exist_ok=True)\nwith tarfile.open('+repr(REMOTE+'/code.tar.gz')+') as t:t.extractall(p,filter="data")')
        if args.component:
          previous=n.config(APP);previous=previous.get('custom_compose_config',previous)
          if isinstance(previous,str):import yaml;previous=yaml.safe_load(previous)
          cfg=json.loads(json.dumps(previous))
          service=args.component
          volumes=cfg['services'][service]['volumes']
          matches=[i for i,v in enumerate(volumes) if v.startswith(REMOTE+'/revisions/') and v.endswith('/'+service+':/app:ro')]
          if len(matches)!=1:raise RuntimeError('Expected the isolated pilot source mount')
          volumes[matches[0]]=REMOTE+'/revisions/'+revision+'/'+service+':/app:ro'
          if service=='worker':configure_worker(cfg)
          try:print(n.update(APP,cfg))
          except Exception:
            n.update(APP,previous)
            raise
          manifest=PRIVATE/'deployment.json'
          metadata=json.loads(manifest.read_text()) if manifest.exists() else {}
          metadata[service+'_revision']=revision
          manifest.write_text(json.dumps(metadata))
          return
        vpn_id=json.loads(n.python("from truenas_api_client import Client\nimport json\nwith Client() as c: print(json.dumps(next(k for k,v in c.call('app.container_ids','mochi-voice',{'alive_only':True}).items() if v.get('service_name')=='vpn')))"))
        cfg=compose(s,original['services']['mochi'],vpn_id,revision)
        configure_worker(cfg)
        (PRIVATE/'deployment.json').write_text(json.dumps({'revision':revision,'personal_config_before':baseline}))
        print(n.update(APP,cfg,create=True))
        return
    finally:n.close()

if __name__=='__main__':main()
