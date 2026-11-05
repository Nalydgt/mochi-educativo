"""Run an isolated NAS CPU optimization trial; production voice stays selected."""
import base64
import argparse
import json
from pathlib import Path
import paramiko

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
mode=parser.add_mutually_exclusive_group()
mode.add_argument('--hybrid',action='store_true')
mode.add_argument('--decoder',action='store_true')
args=parser.parse_args()
remote='/home/truenas_admin/mochi-voice-benchmark'
client=paramiko.SSHClient();client.load_host_keys(str(Path.home()/'.ssh/known_hosts'))
client.set_missing_host_key_policy(paramiko.RejectPolicy())
client.connect('192.168.8.245',username='truenas_admin',key_filename=str(Path.home()/'.ssh/truenas_audit_ed25519'),
 timeout=10,look_for_keys=False,allow_agent=False)
sftp=client.open_sftp()
for directory in (remote,remote+'/code',remote+'/results'):
    try:sftp.mkdir(directory,mode=0o700)
    except IOError:pass
for path in (root/'services/spanish_voice/benchmark_supervisor.py',root/'services/spanish_voice/cpp_trial.py',
             root/'services/spanish_voice/cpp_trial.sh',root/'services/spanish_voice/hybrid_trial.py',
             root/'services/spanish_voice/hybrid_t3.py',root/'services/spanish_voice/hybrid_t3.cpp',
             root/'services/spanish_voice/hybrid_parity.py',root/'services/spanish_voice/export_hybrid_artifacts.py'):
    destination=remote+'/code/'+path.name
    sftp.put(str(path),destination+'.partial');sftp.posix_rename(destination+'.partial',destination)
path=root/'services/spanish_voice/decoder_trial.py'
sftp.put(str(path),remote+'/code/decoder_trial.py.partial');sftp.posix_rename(remote+'/code/decoder_trial.py.partial',remote+'/code/decoder_trial.py')
sftp.close()
assets='/home/truenas_admin/mochi-spanish-voice/assets'
profile=json.loads((root/'.runtime/nas-approved-voice-profile.json').read_text())
assets+='-'+profile['profile_id'][:16]
compose={'services':{'benchmark':{'image':'python:3.11-slim','restart':'no','working_dir':'/app',
    'entrypoint':['sh','-c','apt-get update -qq && apt-get install -y --no-install-recommends build-essential cmake pkg-config git ca-certificates libgomp1 libsndfile1 sox >/results/system.log 2>&1 && exec /runtime/venv/bin/python /app/benchmark_supervisor.py'],
    'environment':{'OMP_NUM_THREADS':'4','MKL_NUM_THREADS':'4','PKUSEG_HOME':'/runtime/pkuseg',
        'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','NUMBA_CACHE_DIR':'/results/numba','PYTHONUNBUFFERED':'1','TQDM_DISABLE':'1',
        'MOCHI_BENCH_MODE':'decoder' if args.decoder else 'hybrid','TORCHINDUCTOR_CACHE_DIR':'/compile/torchcache','TORCHINDUCTOR_COMPILE_THREADS':'2','TORCHINDUCTOR_FREEZING':'1'},
    'volumes':[remote+'/code:/app:ro',remote+'/results:/results',assets+':/assets:ro',
        'voice-runtime:/runtime:ro','mochi-data:/shared:ro','compiler-cache:/compile'],'cpus':8,'mem_limit':'8g'}},
    'volumes':{'voice-runtime':{'external':True,'name':'ix-mochi-spanish-voice_runtime'},
        'mochi-data':{'external':True,'name':'ix-mochi-voice_mochi-data'},'compiler-cache':{}}}
encoded=base64.b64encode(json.dumps(compose).encode()).decode()
source='CONFIG='+repr(encoded)+'\n'+'''
from truenas_api_client import Client
import base64,json,time
config=json.loads(base64.b64decode(CONFIG))
with Client() as c:
 exists=any(app.get('id')=='mochi-voice-benchmark' for app in c.call('app.query'))
 job=c.call('app.update','mochi-voice-benchmark',{'custom_compose_config':config}) if exists else c.call('app.create',{'app_name':'mochi-voice-benchmark','custom_app':True,'custom_compose_config':config})
 deadline=time.monotonic()+120
 while time.monotonic()<deadline:
  state=c.call('core.get_jobs',[['id','=',job]])[0]['state']
  if state in ('SUCCESS','FAILED','ABORTED'):
   print(json.dumps({'job_id':job,'state':state}))
   if state!='SUCCESS':raise RuntimeError('Benchmark deployment job failed')
   break
  time.sleep(1)
 else:raise TimeoutError('Benchmark deployment is still running')
 app=next(app for app in c.call('app.query') if app['id']=='mochi-voice-benchmark')
 print(json.dumps({'app_state':app['state'],'production_changed':False}))
 if app['state']=='STOPPED':print('Configuration staged; start the isolated benchmark explicitly to run it.')
'''
stdin,stdout,stderr=client.exec_command('python3 -',timeout=135)
stdin.write(source);stdin.channel.shutdown_write()
output=stdout.read().decode();error=stderr.read().decode();status=stdout.channel.recv_exit_status();client.close()
if status:raise RuntimeError('Benchmark deployment failed: '+error[:300])
print(output.strip())
