"""Publish a local firmware image with the gateway's existing signing key."""
import argparse
import json
from pathlib import Path
import shutil
import sys

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'gateway'))
from artifacts import ArtifactSigner,file_manifest,verify_manifest

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('image',type=Path)
parser.add_argument('--data',type=Path,required=True)
parser.add_argument('--version',required=True)
args=parser.parse_args()
if not args.image.is_file() or not 16<args.image.stat().st_size<=4*1024*1024:
    raise SystemExit('Expected an ESP32-S3 application image no larger than 4 MiB')
if args.image.open('rb').read(1)!=b'\xe9':
    raise SystemExit('Not an ESP application image')
key=args.data/'artifact-signing-key.pem'
if not key.is_file():
    raise SystemExit('Use the existing gateway signing key; publication never creates a replacement')
destination=args.data/'updates'; destination.mkdir(parents=True,exist_ok=True)
signer=ArtifactSigner(key)
previous=destination/'manifest.json'
if previous.exists() and (destination/'firmware.bin').exists():
    old_envelope=json.loads(previous.read_text(encoding='utf-8'))
    old_payload=verify_manifest(old_envelope,signer.public_key())
    old_image=destination/'firmware.bin'
    actual=file_manifest(old_image,kind='firmware',version=old_payload['version'])
    if actual['sha256']!=old_payload['sha256'] or actual['size']!=old_payload['size']:
        raise SystemExit('The previous published image failed integrity verification')
    archive=destination/'archive'/old_payload['sha256'];archive.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(old_image,archive/'firmware.bin')
    shutil.copyfile(previous,archive/'manifest.json')
temporary=destination/'firmware.bin.partial'; shutil.copyfile(args.image,temporary)
envelope=signer.sign(file_manifest(temporary,kind='firmware',version=args.version))
manifest=destination/'manifest.json.partial'; manifest.write_text(json.dumps(envelope),encoding='utf-8')
temporary.replace(destination/'firmware.bin'); manifest.replace(destination/'manifest.json')
print('Signed firmware published locally:',args.version)
