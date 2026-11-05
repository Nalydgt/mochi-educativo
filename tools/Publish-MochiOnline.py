"""Publish an OTA release through the NAS; the device installs it over Wi-Fi.

The existing signing key remains inside the gateway data volume. This command
does not flash a serial port, replace the key, or modify the device's settings.
"""
import argparse
import hashlib
import json
from pathlib import Path

from nas import NAS

ROOT = Path(__file__).resolve().parents[1]


def image_version(image):
    content = image.read_bytes()
    if not 112 <= len(content) <= 4194304 or content[0] != 0xe9 or content[32:36] != b'\x32\x54\xcd\xab':
        raise ValueError('Expected a built ESP-IDF OTA application up to 4 MiB')
    version = content[48:80].split(b'\0', 1)[0].decode('ascii')
    name = content[80:112].split(b'\0', 1)[0].decode('ascii')
    if name != 'mochi' or not version or len(version) > 31:
        raise ValueError('Expected the Mochi application with an embedded version')
    return version, hashlib.sha256(content).hexdigest()


def source_bind(config):
    sources = []
    for value in config['services']['mochi'].get('volumes', []):
        if isinstance(value, str):
            pieces = value.split(':')
            if len(pieces) >= 2 and pieces[1] == '/app': sources.append(pieces[0])
        elif isinstance(value, dict) and value.get('target') == '/app' and value.get('type') == 'bind':
            sources.append(value['source'])
    if len(sources) != 1 or not sources[0].startswith('/'):
        raise ValueError('Expected the existing absolute gateway source bind')
    return sources[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, default=ROOT/'firmware/build-ota/mochi.bin')
    parser.add_argument('--settings', type=Path, default=ROOT/'.runtime/nas.json')
    args = parser.parse_args()
    version, digest = image_version(args.image)
    settings = json.loads(args.settings.read_text(encoding='utf-8'))
    nas = NAS(settings)
    try:
        remote = source_bind(nas.config('mochi-voice'))+'/.ota-candidates/'+digest
        nas.python('from pathlib import Path\nPath('+repr(remote)+').mkdir(mode=0o700,parents=True,exist_ok=True)')
        nas.upload(args.image, remote+'/firmware.bin')
        nas.upload(ROOT/'tools/Publish-MochiUpdate.py', remote+'/publish.py')
        source = 'VERSION='+repr(version)+'\nDIGEST='+repr(digest)+'\n'+'''
from pathlib import Path
import hashlib,runpy,sys,json
from app import Settings
root=Path('/app/.ota-candidates')/DIGEST
image=root/'firmware.bin'
if hashlib.sha256(image.read_bytes()).hexdigest()!=DIGEST:
 raise ValueError('Uploaded OTA integrity mismatch')
settings=Settings.from_env()
if not (settings.data_dir/'artifact-signing-key.pem').is_file():
 raise ValueError('The original signing key is unavailable; no replacement will be created')
sys.argv=[str(root/'publish.py'),str(image),'--data',str(settings.data_dir),'--version',VERSION]
runpy.run_path(str(root/'publish.py'),run_name='__main__')
print(json.dumps({'published':True,'version':VERSION,'sha256':DIGEST,'usb_required':False}),flush=True)
'''
        command = "cd /app\n/data/gateway-runtime/venv/bin/python - <<'MOCHI_PUBLISH'\n"+source+'\nMOCHI_PUBLISH'
        print(nas.container('mochi-voice', 'mochi', command, timeout=60), flush=True)
        print('On Mochi: Ajustes > Bateria y actualizar > Buscar actualizacion', flush=True)
    finally:
        nas.close()


if __name__ == '__main__': main()
