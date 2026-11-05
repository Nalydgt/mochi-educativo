"""Stage the isolated wake-name training service on the existing TrueNAS server.

Reuses the shared data volume without printing credentials.
The production application and its selected voice are not changed.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import tarfile

import paramiko

ROOT=Path(__file__).resolve().parents[1]
REMOTE='/home/truenas_admin/mochi-integral'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inspect-only',action='store_true')
    parser.add_argument('--data-volume',default='ix-mochi-voice_mochi-data',help='Verified from the production container mountinfo')
    parser.add_argument('--debug-training',action='store_true')
    args=parser.parse_args()
    client=paramiko.SSHClient(); client.load_host_keys(str(Path.home()/'.ssh/known_hosts'))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    client.connect('192.168.8.245',username='truenas_admin',key_filename=str(Path.home()/'.ssh/truenas_audit_ed25519'),
                   timeout=10,look_for_keys=False,allow_agent=False)
    def execute(source,timeout=60):
        stdin,stdout,stderr=client.exec_command('python3 -',timeout=timeout)
        stdin.write(source); stdin.channel.shutdown_write()
        output=stdout.read().decode(); error=stderr.read().decode()
        if stdout.channel.recv_exit_status(): raise RuntimeError('NAS operation failed: '+error[:500])
        return output
    config=json.loads(execute("from truenas_api_client import Client\nimport json\nwith Client() as c: print(json.dumps(c.call('app.config','mochi-voice')))\n"))
    snapshot=ROOT/'.runtime/nas-implementation-before.json'
    if not snapshot.exists(): snapshot.write_text(json.dumps(config,indent=2),encoding='utf-8')
    compose=config.get('custom_compose_config',config)
    if isinstance(compose,str):
        import yaml; compose=yaml.safe_load(compose)
    production=next(s for s in compose['services'].values() if 'MOCHI_TOKEN' in s.get('environment',{}))
    shared=next(v for v in production['volumes'] if (isinstance(v,str) and v.split(':')[1]=='/data') or (isinstance(v,dict) and v.get('target')=='/data'))
    source=shared.split(':')[0] if isinstance(shared,str) else shared['source']
    if source in compose.get('volumes',{}):
        spec=compose['volumes'][source]
        source=spec.get('name',source)
        if not spec.get('name'):
            source=args.data_volume
    print('Existing services:',', '.join(compose['services']),flush=True)
    print('Shared data:',source,flush=True)
    if args.inspect_only:
        client.close(); return
    archive=ROOT/'.runtime/mochi-integral-code.tar.gz'
    with tarfile.open(archive,'w:gz') as output:
        for directory,target in [('gateway','gateway'),('services/wake','wake'),('.references/micro-wake-word','micro-wake-word')]:
            for path in (ROOT/directory).rglob('*'):
                if not path.is_file() or any(p in {'.git','.venv','__pycache__','.pytest_cache','data'} or p.endswith('.egg-info') for p in path.relative_to(ROOT/directory).parts) or path.name=='.env': continue
                output.add(path,arcname=target+'/'+path.relative_to(ROOT/directory).as_posix(),recursive=False)
    sftp=client.open_sftp()
    for directory in [REMOTE]:
        try: sftp.mkdir(directory,mode=0o700)
        except IOError: pass
    sftp.put(str(archive),REMOTE+'/code.tar.gz')
    execute("import tarfile\nwith tarfile.open('"+REMOTE+"/code.tar.gz') as t: t.extractall('"+REMOTE+"',filter='data')\n")
    sftp.close()
    volumes={'training-runtime':{}}
    if source.startswith('/'):
        shared_mount=source+':/shared'
    else:
        # TrueNAS prefixes non-external Compose volumes with its project name.
        volumes['shared-data']={'external':True,'name':source}; shared_mount='shared-data:/shared'
    lab={'services':{
        'training':{'image':'python:3.11-slim','restart':'unless-stopped','working_dir':'/app/wake',
            'entrypoint':['sh','/app/wake/start.sh'],
            'environment':{'MOCHI_WAKE_DIR':'/shared/wake-models','MOCHI_TRAIN_VOICES':'/shared/voices','OMP_NUM_THREADS':'2','CUDA_VISIBLE_DEVICES':'-1',
                'MOCHI_TRAIN_REVISION':hashlib.sha256(b''.join((ROOT/'services/wake'/name).read_bytes()
                    for name in ('worker.py','train_name.py','placement.py'))).hexdigest()},
            'volumes':[REMOTE+':/app:ro',shared_mount,'training-runtime:/runtime'],'cpus':2,'mem_limit':'8g'}},'volumes':volumes}
    if args.debug_training:
        lab['services']['training']['entrypoint']=['sh','-c','exec sh /app/wake/start.sh >>/runtime/startup.log 2>&1']
    encoded=base64.b64encode(json.dumps(lab).encode()).decode()
    result=execute("from truenas_api_client import Client\nimport json,base64\nconfig=json.loads(base64.b64decode("+repr(encoded)+"))\nwith Client() as c:\n apps=c.call('app.query')\n exists=any(a.get('id')=='mochi-integral-lab' for a in apps)\n job=c.call('app.update','mochi-integral-lab',{'custom_compose_config':config}) if exists else c.call('app.create',{'app_name':'mochi-integral-lab','custom_app':True,'custom_compose_config':config})\n print(json.dumps({'job_id':job}))\n",timeout=90)
    print(result,flush=True); client.close()


if __name__=='__main__': main()
