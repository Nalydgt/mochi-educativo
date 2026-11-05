"""Read-only container diagnostics via a temporary disabled NAS admin task."""
import json,shlex,time
from pathlib import Path
from pilot import NAS,settings,ROOT,PRIVATE,REMOTE,credentials
source='''import json,os,subprocess
from pathlib import Path
result={}
for name in ['web','worker','relay']:
 p=subprocess.run(['docker','logs','--tail','12','ix-peluqo-pilot-'+name+'-1'],capture_output=True,text=True,timeout=15)
 result[name]=(p.stdout+p.stderr)[-2000:]
f=Path('/home/truenas_admin/peluqo-pilot/diagnostic.json');f.write_text(json.dumps(result));os.chown(f,950,950);f.chmod(0o600)
'''
local=PRIVATE/'diagnostic-runner.py';local.write_text(source)
n=NAS(settings())
try:
 n.upload(local,REMOTE+'/diagnostic.py')
 task={'user':'root','command':'/usr/bin/python3 '+shlex.quote(REMOTE+'/diagnostic.py'),'description':'Temporary read-only PELUQO container diagnosis','enabled':False,'stdout':False,'stderr':False}
 print(n.python('CONFIG='+repr(task)+'\n'+'''from truenas_api_client import Client
import json,time
with Client() as c:
 task=c.call('cronjob.create',CONFIG)
 try:
  job=c.call('cronjob.run',task['id'],False)
  while True:
   state=c.call('core.get_jobs',[['id','=',job]])[0]['state']
   if state in ('SUCCESS','FAILED','ABORTED'):break
   time.sleep(.3)
  print(json.dumps({'diagnostic':state}))
 finally:c.call('cronjob.delete',task['id'])
''',timeout=90))
 out=n.python('from pathlib import Path\nprint(Path('+repr(REMOTE+'/diagnostic.json')+').read_text())')
 for v in credentials().values():out=out.replace(v,'[private]')
 print(out)
finally:n.close()
