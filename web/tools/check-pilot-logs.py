import json,shlex
from pilot import NAS,settings
n=NAS(settings())
try:
 print(n.container('peluqo-pilot','web',"pwd",timeout=15))
 print(n.container('hermes-agent','hermes-agent',"python -c \"from pathlib import Path; import json; p=Path('/opt/data/profiles/peluqo/logs'); print(json.dumps([f.name for f in p.iterdir()] if p.is_dir() else []))\"",timeout=15))
finally:n.close()
