"""Stage or activate ElevenLabs on the existing NAS without a USB connection.

Staging uses the system disk and works even when the application pool is down.
Activation requires healthy application storage, keeps the existing data/VPN,
and restores the old compose configuration if the new service fails its checks.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen

from nas import NAS

ROOT = Path(__file__).resolve().parents[1]


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def pool_status(nas):
    return json.loads(nas.python('''
from truenas_api_client import Client
import json
with Client() as c:
 print(json.dumps([{'name':p['name'],'status':p['status'],'healthy':p['healthy']}
  for p in c.call('pool.query',[['name','=','Prueba1']])]))
''', timeout=15))


def build_config(current, stage, metadata):
    """Change only the gateway's source bind and selected speech provider."""
    result = deepcopy(current)
    service = result['services']['mochi']
    environment = service.setdefault('environment', {})
    if isinstance(environment, list):
        environment = dict(item.split('=', 1) for item in environment if '=' in item)
        service['environment'] = environment
    environment.pop('ELEVENLABS_API_KEY', None)
    environment.update(MOCHI_VOICE_PROVIDER='elevenlabs',
        ELEVENLABS_API_KEY_FILE='/run/secrets/elevenlabs-api.key',
        ELEVENLABS_VOICE_ID=metadata['voice_id'],
        ELEVENLABS_MODEL_ID=metadata.get('model_id', 'eleven_flash_v2_5'),
        ELEVENLABS_VOICE_REVISION=metadata['source_revision'])
    volumes = service.get('volumes', [])
    updated = []; source_binds = 0
    for binding in volumes:
        target = binding.split(':')[1] if isinstance(binding, str) and ':' in binding else binding.get('target') if isinstance(binding, dict) else None
        if target == '/app':
            updated.append(stage['code_remote']+':/app:ro'); source_binds += 1
        elif target != '/run/secrets/elevenlabs-api.key':
            updated.append(binding)
    if source_binds != 1:
        raise ValueError('Expected exactly one existing gateway source bind at /app')
    updated.append(stage['key_remote']+':/run/secrets/elevenlabs-api.key:ro')
    service['volumes'] = updated
    return result


def stage_code(nas, settings, metadata, key_file, output):
    sources = [p for p in (ROOT/'gateway').iterdir() if p.is_file()
        and not p.name.startswith('test_') and p.suffix in {'.py', '.sh', '.txt', '.toml', '.lock'}]
    manifest = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(sources)}
    code_hash = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    remote = '/home/'+settings['user']+'/mochi-elevenlabs-staging'
    code_remote = remote+'/gateway-'+code_hash[:16]
    nas.python('from pathlib import Path\np=Path('+repr(remote)+')\n'
        'p.mkdir(mode=0o700,exist_ok=True)\np.chmod(0o700)\n'
        'Path('+repr(code_remote)+').mkdir(mode=0o700,exist_ok=True)')
    for path in sources:
        nas.upload(path, code_remote+'/'+path.name)
    nas.upload(key_file, remote+'/api.key')
    with nas.client.open_sftp() as sftp:
        sftp.chmod(remote+'/api.key', 0o600)
    # Verify every staged source before changing any running service.
    nas.python('MANIFEST='+repr(manifest)+'\nROOT='+repr(code_remote)+'\n'+'''
from pathlib import Path
import hashlib
for name,expected in MANIFEST.items():
 if hashlib.sha256((Path(ROOT)/name).read_bytes()).hexdigest()!=expected:
  raise ValueError('Staged source integrity check failed')
print('Staged source integrity verified',flush=True)
''')
    result = {'staged_utc':datetime.now(timezone.utc).isoformat(),
        'code_remote':code_remote, 'code_sha256':code_hash, 'files':manifest,
        'key_remote':remote+'/api.key', 'voice_id':metadata['voice_id'],
        'source_revision':metadata['source_revision'], 'activated':False}
    save(output, result)
    print(json.dumps({k:v for k,v in result.items() if k != 'files'}), flush=True)
    return result


def verify_gateway(settings, metadata, timeout=180):
    token = (ROOT/settings['device_key_file']).read_text().strip()
    base = 'http://'+settings['host']+':8765'
    headers = {'Authorization':'Bearer '+token}
    deadline = time.monotonic()+timeout
    while time.monotonic() < deadline:
        try:
            with urlopen(Request(base+'/health', headers=headers), timeout=8) as response:
                health = json.load(response)
            if (health.get('speech_loaded') and health.get('voice_provider') == 'elevenlabs'
                    and health.get('voice_installed') and health.get('elevenlabs_voice_id') == metadata['voice_id']):
                break
        except (OSError, ValueError):
            pass
        time.sleep(1)
    else:
        raise TimeoutError('ElevenLabs gateway did not become ready')
    request = Request(base+'/v1/say', data=json.dumps({'text':'Hola, soy Mochi.'}).encode(),
        headers={**headers, 'Content-Type':'application/json'})
    with urlopen(request, timeout=35) as response:
        audio = response.read(1440001)
        if response.headers.get('X-Mochi-Sample-Rate') != '16000' or not audio or len(audio)%2 or len(audio)>1440000:
            raise ValueError('The installed gateway did not return valid PCM16')
    return health


def activate(nas, settings, metadata, stage, output):
    if stage['voice_id'] != metadata['voice_id'] or stage['source_revision'] != metadata['source_revision']:
        raise ValueError('Staged source and selected clone do not match')
    pools = pool_status(nas)
    if not pools or not all(p['healthy'] and p['status'] == 'ONLINE' for p in pools):
        raise RuntimeError('Application storage is not healthy: '+json.dumps(pools))
    current = nas.config('mochi-voice')
    if 'services' not in current:
        raise ValueError('Unexpected TrueNAS compose configuration; no application changed')
    updated = build_config(current, stage, metadata)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = ROOT/'.runtime'/('elevenlabs-deployment-'+stamp)/'compose.private.json'
    save(backup, current)
    nas.upload(backup, stage['code_remote']+'/compose-before.private.json')
    try:
        print(nas.update('mochi-voice', updated), flush=True)
        verify_gateway(settings, metadata)
    except Exception:
        print('Activation failed; restoring the previous gateway configuration', flush=True)
        nas.update('mochi-voice', current)
        raise
    stage.update(activated=True, activated_utc=datetime.now(timezone.utc).isoformat(),
        rollback_config=str(backup), gateway_pcm_verified=True, physical_device_verified=False)
    save(output, stage)
    print('ElevenLabs active; gateway PCM verified; data volumes and VPN retained', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['stage', 'activate', 'status', 'rollback'])
    parser.add_argument('--settings', type=Path, default=ROOT/'.runtime/nas.json')
    parser.add_argument('--metadata', type=Path, default=ROOT/'.runtime/elevenlabs-voice03.json')
    parser.add_argument('--key-file', type=Path, default=ROOT/'.runtime/elevenlabs-api.key')
    parser.add_argument('--stage', type=Path, default=ROOT/'.runtime/elevenlabs-stage.json')
    parser.add_argument('--backup', type=Path)
    args = parser.parse_args()
    settings = json.loads(args.settings.read_text(encoding='utf-8'))
    nas = NAS(settings)
    try:
        if args.command == 'status':
            print(json.dumps(pool_status(nas)), flush=True)
        elif args.command == 'rollback':
            if not args.backup:
                raise ValueError('Specify --backup with the saved private compose JSON')
            print(nas.update('mochi-voice', json.loads(args.backup.read_text(encoding='utf-8'))), flush=True)
        else:
            metadata = json.loads(args.metadata.read_text(encoding='utf-8'))
            if metadata.get('requires_verification'):
                raise ValueError('Complete ElevenLabs verification first')
            if args.command == 'stage':
                stage_code(nas, settings, metadata, args.key_file, args.stage)
            else:
                activate(nas, settings, metadata, json.loads(args.stage.read_text(encoding='utf-8')), args.stage)
    finally:
        nas.close()


if __name__ == '__main__': main()
