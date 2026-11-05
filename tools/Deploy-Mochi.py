"""Stage, validate and activate the local voice stack with private NAS settings.

Never changes the selected voice profile or the VPN namespace. Stage leaves the
installed gateway in service; activation requires a recorded passing comparison.
"""
import argparse
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from urllib.request import Request,urlopen

from nas import NAS

ROOT=Path(__file__).resolve().parents[1]


def wait_gateway(url,token,timeout=180):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        try:
            with urlopen(Request(url+'/health',headers={'Authorization':'Bearer '+token}),timeout=5) as response:
                status=json.load(response)
            if status.get('speech_loaded') and status.get('voice_installed'):
                print(json.dumps({'gateway_ready':url,'fast_enabled':status.get('fast_conversation_enabled')}),flush=True)
                return
        except Exception:pass
        time.sleep(2)
    raise TimeoutError('Gateway did not become ready')


def model_config(nas,settings):
    current=nas.config('mochi-local-model')
    service=copy.deepcopy(current['services']['model'])
    command=service['command']
    command[command.index('--ctx-size')+1]='8192'
    # A distinct process/attention cache leaves Hermes' 65,536-token slot intact.
    service['ports']=[settings['host']+':8776:8769']
    service['mem_limit']='4g'
    return {'services':{'model':service}}


def stage(nas,settings):
    target=settings['gateway_remote']+'-next'
    nas.python('from pathlib import Path\nPath('+repr(target)+').mkdir(mode=0o700,exist_ok=True)')
    compact=(ROOT/'profiles/mochi/SOUL-VOICE.md').read_text(encoding='utf-8')
    nas.container('hermes-agent','hermes-agent',"python - <<'PY'\n"+'CONTENT='+repr(compact)+'\n'+'''
from pathlib import Path
import os
root=Path('/opt/data/profiles/mochi');path=root/'SOUL-VOICE.md'
if not path.exists():
    path.write_text(CONTENT);owner=root.stat();os.chown(path,owner.st_uid,owner.st_gid)
print('Compact voice identity ready; original SOUL preserved')
PY''')
    for path in (ROOT/'gateway').iterdir():
        if path.is_file() and not path.name.startswith('test_') and path.suffix in ('.py','.sh','.txt','.toml','.lock'):
            nas.upload(path,target+'/'+path.name)
    print(nas.update('mochi-conversation',model_config(nas,settings),create=True),flush=True)
    source=nas.config('mochi-voice')
    service=copy.deepcopy(source['services']['mochi'])
    service.pop('network_mode',None);service.pop('depends_on',None)
    service['command']=['/data/venv/bin/uvicorn','app:app_factory','--factory','--host','0.0.0.0','--port','8765','--no-access-log']
    service['working_dir']='/app'
    service['ports']=[settings['host']+':8777:8765']
    service['volumes']=[target+':/app:ro','mochi-data:/data',settings['profile_host']+':/profile:ro']
    env=service['environment']
    env.update({'MOCHI_DATA_DIR':'/data/optimization-20261026/candidate','MOCHI_FAST_ENABLED':'1',
        'MOCHI_FAST_URL':'http://'+settings['host']+':8776','MOCHI_FAST_KEY':(ROOT/settings['model_key_file']).read_text().strip(),
        'MOCHI_PROFILE_DIR':'/profile','MOCHI_MEMORY_REVIEW_ENABLED':'0','MOCHI_HERMES_WARMUP':'0'})
    print(nas.update('mochi-voice-next',{'services':{'mochi':service},'volumes':{
        'mochi-data':{'external':True,'name':'ix-mochi-voice_mochi-data'}}},create=True),flush=True)
    wait_gateway('http://'+settings['host']+':8777',env['MOCHI_TOKEN'])


def activate(nas,settings,report):
    result=json.loads(report.read_text(encoding='utf-8'))
    if result.get('accepted') is not True or result.get('paired_questions')!=20:
        raise ValueError('A passing 20-question comparison is required before activation')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup=ROOT/'.runtime'/('activation-'+stamp);backup.mkdir(mode=0o700)
    current=nas.config('mochi-voice')
    previous_memory=current['services']['mochi']['environment'].get('MOCHI_MEMORY_PATH','/data/memory.sqlite3')
    (backup/'gateway.json').write_text(json.dumps(current,indent=2))
    # Source/config backup includes all private settings and the journal's WAL.
    print(nas.container('mochi-voice','mochi',"/data/venv/bin/python - <<'PY'\n"+
        "import sqlite3,shutil\nfrom pathlib import Path\nroot=Path('/data/backups/"+stamp+"');root.mkdir(parents=True,mode=0o700)\n"+
        'with sqlite3.connect('+repr(previous_memory)+") as source,sqlite3.connect(root/'memory.sqlite3') as target:source.backup(target)\n"+
        "shutil.copytree('/app',root/'gateway')\nprint('Gateway and durable memory backed up')\nPY"),flush=True)
    # The profile owns its database path via a symlinked local directory, using
    # its existing host dataset; no catalog-managed Hermes volumes are changed.
    plugin_files={name:(ROOT/'services/hermes_memory'/name).read_text(encoding='utf-8') for name in ('__init__.py','plugin.yaml')}
    plugin_files['memory_store.py']=(ROOT/'gateway/memory_store.py').read_text(encoding='utf-8')
    plugin_files['SOUL-VOICE.md']=(ROOT/'profiles/mochi/SOUL-VOICE.md').read_text(encoding='utf-8')
    # Hermes can access the gateway journal through a bind mount installed by
    # a host path, instead of a second copy of conversations.
    profile=settings['profile_host']
    # Move the database into the profile dataset, then mount the directory into
    # the gateway. Keep the original and the backup for rollback.
    shared=profile+'/mochi-shared'
    print(nas.container('hermes-agent','hermes-agent',"python - <<'PY'\n"+
        'FILES='+repr(plugin_files)+'\nSTAMP='+repr(stamp)+'\nDEVICE='+repr(settings['device'])+'\n'+'''
from pathlib import Path
import os,json,shutil,yaml
root=Path('/opt/data/profiles/mochi');owner=root.stat()
for directory in (root/'plugins',root/'plugins/mochi-local'):
    directory.mkdir(exist_ok=True);os.chown(directory,owner.st_uid,owner.st_gid)
os.setgroups([owner.st_gid]);os.setgid(owner.st_gid);os.setuid(owner.st_uid)
backup=root/'backups'/('voice-'+STAMP);backup.mkdir(parents=True,mode=0o700)
for name in ('config.yaml','SOUL.md','memories/MEMORY.md','memories/USER.md'):
    path=root/name
    if path.exists():
        target=backup/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
plugin=root/'plugins/mochi-local';plugin.mkdir(parents=True,exist_ok=True)
for name,content in FILES.items():
    target=root/name if name=='SOUL-VOICE.md' else plugin/name
    target.write_text(content);os.chown(target,owner.st_uid,owner.st_gid)
shared=root/'mochi-shared';shared.mkdir(exist_ok=True);os.chown(shared,owner.st_uid,owner.st_gid);shared.chmod(0o2770)
sidecar=root/'mochi-local.json'
sidecar.write_text(json.dumps({'database':str(shared/'memory.sqlite3'),'device':DEVICE}));os.chown(sidecar,owner.st_uid,owner.st_gid)
print('Hermes profile backed up; local provider installed')
PY'''),flush=True)
    # Copy via the authenticated container session; never expose conversation
    # contents through stdout or stage them in the public source tree.
    service=current['services']['mochi']
    for mount in (profile+':/profile:ro',shared+':/shared'):
        if mount not in service['volumes']:service['volumes'].append(mount)
    service['environment'].update({'MOCHI_FAST_ENABLED':'1','MOCHI_FAST_URL':'http://'+settings['host']+':8776',
        'MOCHI_FAST_KEY':(ROOT/settings['model_key_file']).read_text().strip(),'MOCHI_PROFILE_DIR':'/profile',
        'MOCHI_MEMORY_REVIEW_ENABLED':'1','MOCHI_HERMES_WARMUP':'0'})
    # The first new startup migrates /data/memory.sqlite3 in place. SQLite is
    # then shared via /shared; prepare its consistent copy while turns are idle.
    # Activating is a maintenance operation: stop the old writer first.
    nas.stop('mochi-voice')
    # Stage code only after the old process has stopped.
    for path in (ROOT/'gateway').iterdir():
        if path.is_file() and not path.name.startswith('test_') and path.suffix in ('.py','.sh','.txt','.toml','.lock'):
            nas.upload(path,settings['gateway_remote']+'/'+path.name)
    serving_command=service.get('command',['sh','/app/start-container.sh'])
    serving_healthcheck=service.get('healthcheck')
    service['command']=['sleep','infinity']
    service['healthcheck']={'disable':True}
    print(nas.update('mochi-voice',current),flush=True)
    # Journal sharing is finalized inside the gateway so named Docker volumes
    # remain private and need no unrestricted host access.
    print(nas.container('mochi-voice','mochi',"/data/venv/bin/python - <<'PY'\n"+'SOURCE='+repr(previous_memory)+'\n'+'''
import sqlite3,os
from pathlib import Path
source=Path(SOURCE);target=Path('/shared/memory.sqlite3')
if source!=target:
    with sqlite3.connect(source) as a,sqlite3.connect(target) as b:a.backup(b)
target.chmod(0o660);os.chown(target,568,568)
print('Shared journal prepared')
PY'''),flush=True)
    # Shared DB becomes authoritative for the next restart.
    service['environment']['MOCHI_MEMORY_PATH']='/shared/memory.sqlite3'
    service['command']=serving_command
    if serving_healthcheck is None:service.pop('healthcheck',None)
    else:service['healthcheck']=serving_healthcheck
    print(nas.container('hermes-agent','hermes-agent',"python - <<'PY'\n"+'''
from pathlib import Path
import yaml,os
root=Path('/opt/data/profiles/mochi');owner=root.stat();path=root/'config.yaml'
config=yaml.safe_load(path.read_text());config.setdefault('memory',{})['provider']='mochi-local'
tmp=path.with_suffix('.mochi-partial');tmp.write_text(yaml.safe_dump(config,allow_unicode=True,sort_keys=False))
tmp.chmod(0o600);os.chown(tmp,owner.st_uid,owner.st_gid);tmp.replace(path)
print('Profile memory provider selected')
PY'''),flush=True)
    print(nas.update('mochi-voice',current),flush=True)
    print(json.dumps({'activated':True,'private_backup':str(backup)}),flush=True)
    wait_gateway('http://'+settings['host']+':8765',service['environment']['MOCHI_TOKEN'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('stage','activate'))
    parser.add_argument('--settings',type=Path,default=ROOT/'.runtime/nas.json')
    parser.add_argument('--report',type=Path,default=ROOT/'docs/mediciones/20261026-voz-comparacion.json')
    args=parser.parse_args();settings=json.loads(args.settings.read_text(encoding='utf-8'))
    nas=NAS(settings)
    try:
        if args.action=='stage':stage(nas,settings)
        else:activate(nas,settings,args.report)
    finally:nas.close()


if __name__=='__main__':main()
