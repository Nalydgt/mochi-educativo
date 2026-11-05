"""Recover the verified 0.6.3 USB image without writing the NVS region.

Only the original bootloader/partition table and factory application are written.
The existing NVS at 0x9000..0xefff, including new pet namespaces, is preserved.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

root=Path(__file__).resolve().parents[1]
manifest_path=root/'backups/mochi-before-integral-20261022-213144.json'
manifest=json.loads(manifest_path.read_text(encoding='utf-8-sig'))
backup=manifest_path.parent/manifest['file']
image=backup.read_bytes()
if len(image)!=16777216 or hashlib.sha256(image).hexdigest().lower()!=manifest['sha256'].lower():
    raise SystemExit('Verified full-flash backup required')
old_app=root/'backups/mochi-0.6.3-voice-diagnostics-app.bin'
application=old_app.read_bytes()
if image[0x10000:0x10000+len(application)]!=application or application[:1]!=b'\xe9':
    raise SystemExit('The 0.6.3 app does not match the verified device backup')
prefix=root/'.runtime/recovery-063-boot-and-partitions.bin'
prefix.write_bytes(image[:0x9000])
print('Recovering baseline; NVS is outside both write ranges.',flush=True)
result=subprocess.run([sys.executable,'-m','esptool','--chip','esp32s3','--port','COM3',
    '--baud','921600','--before','default-reset','--after','hard-reset','write-flash',
    '0x0',str(prefix),'0x10000',str(old_app)],check=False)
raise SystemExit(result.returncode)
