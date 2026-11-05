"""Back up and enable navigation on the existing NAS, preserving voice and VPN.

Private NAS settings and rollback configuration stay outside version control.
Run the backend tests and build the firmware before using this command.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen

from nas import NAS

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--settings', type=Path, default=ROOT/'.runtime/nas.json')
    parser.add_argument('--prepare-audio-only', action='store_true')
    args = parser.parse_args()
    settings = json.loads(args.settings.read_text(encoding='utf-8'))
    nas = NAS(settings)
    try:
        if not args.prepare_audio_only:
            current = nas.config('mochi-voice')
            stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
            backup = ROOT/'backups'/('navigation-'+stamp)
            backup.mkdir(parents=True)
            (backup/'compose.private.json').write_text(json.dumps(current), encoding='utf-8')
            # Back up code/config and the live journal before changing either.
            remote = settings['gateway_remote']
            nas.python('from pathlib import Path\nimport shutil\nsource=Path('+repr(remote)+')\n'
                       'target=source.parent/'+repr('mochi-before-navigation-'+stamp)+'\n'
                       'shutil.copytree(source,target,ignore=shutil.ignore_patterns("__pycache__"))\n'
                       'target.chmod(0o700)')
            print(nas.container('mochi-voice','mochi', "cd /app\n/data/gateway-runtime/venv/bin/python - <<'PY'\n"+'''
from pathlib import Path
import sqlite3,time,shutil
from app import Settings
root=Path('/data/backups')/('navigation-'+str(int(time.time())));root.mkdir(mode=0o700)
settings=Settings.from_env()
for name,source in [('memory',Path(settings.memory_path)),('navigation',Path('/data/navigation.sqlite3'))]:
 if source.exists():
  with sqlite3.connect(source) as a,sqlite3.connect(root/(name+'.sqlite3')) as b:a.backup(b)
if Path('/profile').exists():shutil.copytree('/profile',root/'profile')
print('Private journal and profile backup completed',flush=True)
PY'''), flush=True)
            for path in (ROOT/'gateway').iterdir():
                if path.is_file() and not path.name.startswith('test_') and path.suffix in {'.py','.sh','.txt','.toml','.lock'}:
                    nas.upload(path, remote+'/'+path.name)
            # Install the exact locked dependencies before the service restarts.
            print(nas.container('mochi-voice','mochi',
                '/data/gateway-runtime/venv/bin/python -m pip install --disable-pip-version-check --no-cache-dir --require-hashes -r /app/requirements.txt >/tmp/mochi-navigation-install.log 2>&1 && cp /app/requirements.txt /data/gateway-runtime/requirements.installed.txt && echo Navigation-dependencies-ready', timeout=180), flush=True)
            current['services']['mochi']['environment']['MOCHI_NAVIGATION_ENABLED'] = '1'
            print(nas.update('mochi-voice', current), flush=True)
        token = Path(settings['device_key_file']).read_text().strip()
        deadline = time.monotonic()+180
        while time.monotonic() < deadline:
            try:
                request = Request('http://'+settings['host']+':8765/health', headers={'Authorization':'Bearer '+token})
                with urlopen(request, timeout=5) as response: status = json.load(response)
                if status.get('speech_loaded') and status.get('navigation_enabled'):
                    print('Navigation ready; existing voice profile: '+str(status['native_voice_profile']), flush=True)
                    break
            except Exception: pass
            time.sleep(2)
        else: raise TimeoutError('Navigation service did not become ready; use the private rollback backup')
        # Preparation is explicit maintenance, never performed at a critical turn.
        print(nas.container('mochi-voice','mochi', "cd /app\n/data/gateway-runtime/venv/bin/python - <<'PY'\n"+'''
from app import Settings
from voice_service import VoiceService
from navigation import CUES
settings=Settings.from_env();speech=VoiceService(settings,settings.local_speech())
for i,text in enumerate(CUES.values(),1):
 pcm=speech.speak(text)
 if not pcm or len(pcm)%2:raise ValueError('Invalid navigation PCM')
 print('Prepared navigation cue %d/%d bytes=%d'%(i,len(CUES),len(pcm)),flush=True)
print('Navigation voice ready; immutable voice profile and decoder steps unchanged',flush=True)
PY''', timeout=600), flush=True)
    finally: nas.close()


if __name__ == '__main__': main()
