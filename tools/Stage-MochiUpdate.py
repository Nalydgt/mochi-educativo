"""Upload a built OTA application to the private NAS for signing in place."""
from pathlib import Path
import hashlib
import paramiko

root=Path(__file__).resolve().parents[1]
image=root/'firmware/build-ota/mochi.bin'
if not image.is_file() or not 16<image.stat().st_size<=4194304 or image.read_bytes()[:1]!=b'\xe9':
    raise SystemExit('Build a valid OTA application first')
client=paramiko.SSHClient();client.load_host_keys(str(Path.home()/'.ssh/known_hosts'))
client.set_missing_host_key_policy(paramiko.RejectPolicy())
client.connect('192.168.8.245',username='truenas_admin',key_filename=str(Path.home()/'.ssh/truenas_audit_ed25519'),
    timeout=10,look_for_keys=False,allow_agent=False)
sftp=client.open_sftp()
destination='/home/truenas_admin/mochi-gateway/firmware-candidate.bin'
sftp.put(str(image),destination+'.partial');sftp.posix_rename(destination+'.partial',destination)
publisher='/home/truenas_admin/mochi-gateway/publish-update.py'
sftp.put(str(root/'tools/Publish-MochiUpdate.py'),publisher+'.partial');sftp.posix_rename(publisher+'.partial',publisher)
sftp.close();client.close()
print('Private OTA candidate staged; SHA256',hashlib.sha256(image.read_bytes()).hexdigest())
