import shlex,json
from pilot import NAS,settings,PRIVATE
n=NAS(settings())
try:
 source='''import inspect,json,os
from pathlib import Path
import hermes_cli.profiles as p
from hermes_cli.config import get_hermes_home
print(json.dumps({'files':[x.name for x in Path(get_hermes_home()).iterdir()],'profile_functions':[x for x in dir(p) if any(k in x for k in ['create','profile','context']) and callable(getattr(p,x))]}))
for name in ['get_profile_dir','list_profiles','create_profile','profile_context','resolve_profile_home']:
 if hasattr(p,name):print(name,inspect.getsource(getattr(p,name)))
'''
 # Read-only source copies let us inspect the actual pinned runtime, not guess APIs.
 extract='''import inspect,base64,json
import hermes_cli.profiles as p
import hermes_cli.auth as a
print(json.dumps({name:base64.b64encode(path.read_bytes()).decode() for name,path in [('profiles.py',Path(p.__file__)),('auth.py',Path(a.__file__)),('api_server.py',Path('/opt/hermes/gateway/platforms/api_server.py')),('run.py',Path('/opt/hermes/gateway/run.py')),('run_agent.py',Path('/opt/hermes/run_agent.py'))]}))
'''.replace('import inspect,base64,json','import inspect,base64,json\nfrom pathlib import Path')
 import base64
 files=json.loads(n.container('hermes-agent','hermes-agent','python -c '+shlex.quote(extract),timeout=30))
 target=PRIVATE/'hermes-current';target.mkdir(exist_ok=True)
 for name,data in files.items():(target/name).write_bytes(base64.b64decode(data))
finally:n.close()
