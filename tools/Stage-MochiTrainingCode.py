"""Update training scripts atomically without interrupting a running child job."""
from pathlib import Path
import paramiko

root=Path(__file__).resolve().parents[1]
client=paramiko.SSHClient();client.load_host_keys(str(Path.home()/'.ssh/known_hosts'))
client.set_missing_host_key_policy(paramiko.RejectPolicy())
client.connect('192.168.8.245',username='truenas_admin',key_filename=str(Path.home()/'.ssh/truenas_audit_ed25519'),
    timeout=10,look_for_keys=False,allow_agent=False)
sftp=client.open_sftp()
# Updating a source file never interrupts the interpreter already using it.
# worker.py takes effect only when the dedicated training app is restarted.
for name in ('train_name.py','worker.py','placement.py','check_stream_parity.py','check_dataset_generalization.py'):
    target='/home/truenas_admin/mochi-integral/wake/'+name
    sftp.put(str(root/'services/wake'/name),target+'.partial')
    sftp.posix_rename(target+'.partial',target)
sftp.close();client.close()
print('Training source staged; worker changes apply at the next service restart.')
