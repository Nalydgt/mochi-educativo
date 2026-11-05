import json,shlex,base64
from pilot import NAS,settings,PRIVATE,credentials
n=NAS(settings())
try:
 source='''import os,json,base64
from pathlib import Path
import agent.secret_scope as s
print(json.dumps({'ports':{k:v for k,v in os.environ.items() if k in ['API_SERVER_PORT','API_SERVER_HOST','A2A_PORT']},'files':{name:base64.b64encode(path.read_bytes()).decode() for name,path in [('secret_scope.py',Path(s.__file__)),('profile_context.py',Path('/opt/hermes/hermes_cli/profile_context.py'))] if path.exists()}}))
'''
 r=json.loads(n.container('hermes-agent','hermes-agent','python -c '+shlex.quote(source),timeout=20))
 print(json.dumps({'ports':r['ports']}))
 for name,data in r['files'].items():(PRIVATE/'hermes-current'/name).write_bytes(base64.b64decode(data))
 original=n.config('mochi-voice');original=original.get('custom_compose_config',original)
 if isinstance(original,str):
  import yaml
  original=yaml.safe_load(original)
 master=original['services']['mochi']['environment']['HERMES_API_KEY']
 source='''import urllib.request,json
result={}
for label,key in [('education',EDUCATION),('personal',PERSONAL)]:
 for path in ['/p/peluqo/v1/toolsets','/p/mochi/v1/models']:
  try:
   with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:30432'+path,headers={'Authorization':'Bearer '+key}),timeout=5) as r:
    data=json.load(r);result[label+path]={'status':r.status,'keys':list(data),'enabled':[x.get('name') for x in data.get('toolsets',[]) if x.get('enabled')]}
  except urllib.error.HTTPError as e:result[label+path]={'status':e.code,'body':e.read().decode()[:250]}
print(json.dumps(result))
'''
 print(n.python('EDUCATION='+repr(credentials()['hermes'])+'\nPERSONAL='+repr(master)+'\n'+source,timeout=30))
finally:n.close()
