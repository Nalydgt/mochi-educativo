"""Deploy the NAS voice runtime; gateway selection is managed separately.

The application on historical port 8775 is the approved active voice.
Redeploying it updates production even though its historical name says trial.
"""
import base64
import argparse
import hashlib
import json
from pathlib import Path
import time
from urllib.request import Request,urlopen

import paramiko

ROOT=Path(__file__).resolve().parents[1]
REMOTE='/home/truenas_admin/mochi-fast-voice'
ARTIFACTS='/home/truenas_admin/mochi-voice-benchmark/results/hybrid-v1'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cpu-wait-policy',choices=('default','passive'),default=None,
                        help='Compare OpenMP waiting behavior without changing the voice profile')
    args=parser.parse_args()
    remote=REMOTE+'-trial'
    app_name='mochi-fast-voice-trial'
    port=8775
    base=json.loads((ROOT/'.runtime/nas-approved-voice-profile.json').read_text())
    client=paramiko.SSHClient();client.load_host_keys(str(Path.home()/'.ssh/known_hosts'))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    client.connect('192.168.8.245',username='truenas_admin',key_filename=str(Path.home()/'.ssh/truenas_audit_ed25519'),
        timeout=10,look_for_keys=False,allow_agent=False)
    sftp=client.open_sftp()
    with sftp.open(ARTIFACTS+'/artifacts.json') as source:metadata=json.load(source)
    profile=base['profile']
    if (not metadata.get('numerical_parity_passed') or metadata['reference_sha256']!=profile['files']['reference.wav'] or
            metadata['source_checkpoint_sha256']!=profile['files'][profile['checkpoint']]):
        raise RuntimeError('The native candidate does not match the approved voice')
    for local,key in (('hybrid_t3.cpp','adapter_sha256'),('hybrid_t3.py','python_adapter_sha256')):
        if hashlib.sha256((ROOT/'services/spanish_voice'/local).read_bytes()).hexdigest()!=metadata[key]:
            raise RuntimeError('The native candidate and serving adapter have different revisions')
    for name,digest in metadata['files'].items():
        if Path(name).name!=name or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('Invalid native artifact manifest')
    profile.update({'backend':'ggml-t3-torch-decoder','native_checkpoint':'t3-ggml-q8.gguf',
        'native_libraries':metadata['native_libraries'],'decoder_threads':metadata['decoder_threads'],
        't3_threads':metadata['t3_threads'],'native_source':{k:metadata[k] for k in
            ('cpp_revision','ggml_revision','adapter_sha256','python_adapter_sha256','source_checkpoint_sha256')}})
    profile['files'].update(metadata['files'])
    profile['decoder_cfm_steps']=4
    identifier=hashlib.sha256(json.dumps(profile,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
    if identifier!='e9924f56a4686f2b4cf0a266c19b4e74ecd056001cb89cdcc8702e2b52169162':
        raise RuntimeError('Rebuilt artifacts differ from the approved four-step voice profile')
    assets=remote+'/assets-'+identifier[:16]
    for path in (remote,remote+'/code',assets):
        try:sftp.mkdir(path,mode=0o700)
        except IOError:pass
    for path in (ROOT/'services/spanish_voice').iterdir():
        if path.suffix not in ('.py','.txt','.md','.sh') or path.name.startswith('test_'):continue
        target=remote+'/code/'+path.name
        sftp.put(str(path),target+'.partial');sftp.posix_rename(target+'.partial',target)
    sftp.close()
    sources={name:ARTIFACTS+'/artifacts/'+name if name in metadata['files'] else
        '/home/truenas_admin/mochi-spanish-voice/assets-'+base['profile_id'][:16]+'/'+name
        for name in profile['files']}
    script='SOURCES='+repr(sources)+'\nFILES='+repr(profile['files'])+'\nDEST='+repr(assets)+'\nPROFILE='+repr(profile)+'\n'+'''
from pathlib import Path
import errno,hashlib,json,os,shutil
for name,filename in SOURCES.items():
 source=Path(filename);target=Path(DEST)/name
 with source.open('rb') as stream:
  if hashlib.file_digest(stream,'sha256').hexdigest()!=FILES[name]:raise RuntimeError('Native staging integrity mismatch')
 if not target.exists():
  try:os.link(source,target)
  except OSError as error:
   if error.errno not in (errno.EPERM,errno.EACCES,errno.EXDEV):raise
   shutil.copyfile(source,target)
temporary=Path(DEST)/'profile.json.partial'
temporary.write_text(json.dumps(PROFILE,ensure_ascii=False));temporary.replace(Path(DEST)/'profile.json')
print('Native candidate assets verified',flush=True)
'''
    stdin,stdout,stderr=client.exec_command('python3 -',timeout=90)
    stdin.write(script);stdin.channel.shutdown_write();print(stdout.read().decode().strip(),flush=True)
    if stdout.channel.recv_exit_status():raise RuntimeError('Candidate asset staging failed: '+stderr.read().decode()[-250:])
    token=(ROOT/'.runtime/mochi-native-voice.key').read_text().strip()
    revision=hashlib.sha256((ROOT/'services/spanish_voice/server.py').read_bytes()).hexdigest()
    compose={'services':{'voice':{'image':'python:3.11-slim','restart':'unless-stopped','working_dir':'/app',
        'entrypoint':['sh','-c','exec sh /app/start.sh >>/fast/startup.log 2>&1'],
        'environment':{'MOCHI_NATIVE_TOKEN':token,'MOCHI_NATIVE_RUNTIME':'/fast','OMP_NUM_THREADS':'8','MOCHI_CODE_REVISION':revision,
            'MKL_NUM_THREADS':'8','TQDM_DISABLE':'1','HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1',
            'PYTHONUNBUFFERED':'1','PYTHONDONTWRITEBYTECODE':'1','NUMBA_CACHE_DIR':'/fast/numba'},
        'ports':[f'192.168.8.245:{port}:8767'],'volumes':[remote+'/code:/app:ro',assets+':/assets:ro',
            'original-runtime:/runtime:ro','fast-runtime:/fast'],'cpus':8,'mem_limit':'8g'}},
        'volumes':{'original-runtime':{'external':True,'name':'ix-mochi-spanish-voice_runtime'},'fast-runtime':{}}}
    if args.cpu_wait_policy is None:
        stdin,stdout,stderr=client.exec_command('python3 -',timeout=15)
        stdin.write("from truenas_api_client import Client\nimport json\nwith Client() as c:\n cfg=c.call('app.config','mochi-fast-voice-trial')\n env=cfg['services']['voice']['environment']\n print(json.dumps({k:env[k] for k in ('OMP_WAIT_POLICY','GOMP_SPINCOUNT') if k in env}))\n")
        stdin.channel.shutdown_write()
        policy=json.loads(stdout.read().decode())
        if stdout.channel.recv_exit_status():raise RuntimeError('Cannot preserve the active CPU scheduling policy')
        compose['services']['voice']['environment'].update(policy)
    if args.cpu_wait_policy=='passive':
        # Torch and the native T3 load separate GNU OpenMP runtimes. Sleeping
        # idle workers avoids two pools competing while only one is computing.
        compose['services']['voice']['environment'].update({'OMP_WAIT_POLICY':'PASSIVE','GOMP_SPINCOUNT':'0'})
    encoded=base64.b64encode(json.dumps(compose).encode()).decode()
    script='CONFIG='+repr(encoded)+'\nAPP_NAME='+repr(app_name)+'\n'+'''
from truenas_api_client import Client
import base64,json,time
config=json.loads(base64.b64decode(CONFIG))
with Client() as c:
 exists=any(app['id']==APP_NAME for app in c.call('app.query'))
 job=c.call('app.update',APP_NAME,{'custom_compose_config':config}) if exists else c.call('app.create',{'app_name':APP_NAME,'custom_app':True,'custom_compose_config':config})
 deadline=time.monotonic()+120
 while time.monotonic()<deadline:
  state=c.call('core.get_jobs',[['id','=',job]])[0]['state']
  if state in ('SUCCESS','FAILED','ABORTED'):
   print(json.dumps({'job_id':job,'state':state}),flush=True)
   if state!='SUCCESS':raise RuntimeError('Native candidate deployment failed')
   break
  time.sleep(1)
 else:raise TimeoutError('Native candidate deployment still running')
 if c.call('app.query',[['id','=',APP_NAME]])[0]['state']=='STOPPED':
  start=c.call('app.start',APP_NAME)
  deadline=time.monotonic()+60
  while time.monotonic()<deadline:
   state=c.call('core.get_jobs',[['id','=',start]])[0]['state']
   if state in ('SUCCESS','FAILED','ABORTED'):
    if state!='SUCCESS':raise RuntimeError('Saved native voice could not start')
    print(json.dumps({'start_job':start,'state':state}),flush=True);break
   time.sleep(1)
  else:raise TimeoutError('Saved native voice start still running')
'''
    stdin,stdout,stderr=client.exec_command('python3 -',timeout=135)
    stdin.write(script);stdin.channel.shutdown_write();print(stdout.read().decode().strip(),flush=True)
    if stdout.channel.recv_exit_status():raise RuntimeError('Native candidate deployment failed: '+stderr.read().decode()[-300:])
    client.close()
    (ROOT/'.runtime/fast-voice-trial-profile.json').write_text(json.dumps({'profile_id':identifier,'profile':profile},indent=2),encoding='utf-8')
    deadline=time.monotonic()+100
    while time.monotonic()<deadline:
        try:
            with urlopen(Request(f'http://192.168.8.245:{port}/health',headers={'Authorization':'Bearer '+token}),timeout=3) as response:health=json.load(response)
            if health.get('ready') and health.get('profile')==identifier:
                print(json.dumps({'candidate_ready':True,'profile':identifier,'gateway_selection_changed':False}),flush=True);return
        except Exception:pass
        time.sleep(2)
    raise RuntimeError('Candidate not ready; production voice selection was preserved')


if __name__=='__main__':main()
