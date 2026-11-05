"""Only report names, never values, if a private credential enters client assets."""
import json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
private=json.loads((root/'.runtime/pilot-secrets.json').read_text())
keys={k:v.encode() for k,v in private.items() if isinstance(v,str) and len(v)>=32 and k not in {'anon','service','cloud_project'}}
found=[]
for file in (root/'.output/public').rglob('*'):
 if file.is_file():
  data=file.read_bytes()
  found.extend({'file':str(file.relative_to(root)),'key':k} for k,v in keys.items() if v in data)
if found:raise SystemExit(json.dumps({'private_credentials_in_client':found}))
print(json.dumps({'client_contains_private_credentials':False,'checked_secret_types':len(keys)}))
