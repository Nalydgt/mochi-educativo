"""Submit a name to the authenticated NAS queue without putting a token in arguments."""
import argparse
import json
from pathlib import Path
import time
from urllib.error import URLError,HTTPError
from urllib.request import Request,urlopen

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('name',nargs='?',default='Mochi')
parser.add_argument('--device',default='mochi-bootstrap')
parser.add_argument('--url',default='http://192.168.8.245:8765')
parser.add_argument('--key-file',type=Path,default=Path('.runtime/mochi-device.key'))
parser.add_argument('--output',type=Path,default=Path('.runtime/initial-wake-job.json'))
args=parser.parse_args(); token=args.key_file.read_text().strip()
headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'}
deadline=time.monotonic()+120
while True:
    try:
        with urlopen(Request(args.url+'/health',headers=headers),timeout=10) as response: health=json.load(response)
        if health.get('wake_worker_enabled'): break
    except (URLError,HTTPError,ValueError): pass
    if time.monotonic()>deadline: raise SystemExit('Gateway name preparer did not become ready')
    time.sleep(1)
request=Request(args.url+'/v1/wake-model/jobs',data=json.dumps({'name':args.name,'device_id':args.device}).encode(),headers=headers)
with urlopen(request,timeout=30) as response: job=json.load(response)
args.output.parent.mkdir(parents=True,exist_ok=True)
args.output.write_text(json.dumps(job,indent=2),encoding='utf-8')
print(json.dumps({'id':job['id'],'stage':job['stage']}),flush=True)
