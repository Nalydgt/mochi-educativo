import json
from pathlib import Path
from pilot import NAS,settings,PRIVATE
n=NAS(settings())
try:
 c=n.config('hermes-agent');c=c.get('custom_compose_config',c)
 if isinstance(c,str):
  import yaml
  c=yaml.safe_load(c)
 (PRIVATE/'hermes-compose.json').write_text(json.dumps(c,indent=2))
 services=json.loads(n.python("from truenas_api_client import Client\nimport json\nwith Client() as c: print(json.dumps(c.call('app.container_ids','hermes-agent',{'alive_only':True})))"))
 print(json.dumps(services))
 service=next(v['service_name'] for v in services.values() if 'hermes' in v['service_name'])
 source="""import os,inspect,json
import hermes_cli.tools_config as t
from hermes_cli.config import load_config,get_hermes_home
c=load_config()
print(json.dumps({'home':str(get_hermes_home()),'tools':c.get('platform_toolsets'),'model':c.get('model'),'gateway':c.get('gateway'),'memory':c.get('memory'),'env_keys':list(os.environ)}))
print(inspect.getsource(t._get_platform_tools))
"""
 import shlex
 print(n.container('hermes-agent',service,'python -c '+shlex.quote(source),timeout=30))
finally:n.close()
