"""Enable only the requested private pilot forwards for the existing NAS user."""
import json
from pilot import NAS,settings,PRIVATE
cfg=settings();n=NAS(cfg)
try:
 # Keep a recovery copy outside source control. Never change global forwarding,
 # password auth, port, bind addresses or any unrelated SSH option.
 old=json.loads(n.python("from truenas_api_client import Client\nimport json\nwith Client() as c: print(json.dumps(c.call('ssh.config')))"))
 backup=PRIVATE/'ssh-before.json'
 if not backup.exists():backup.write_text(json.dumps(old,indent=2))
 marker='# PELUQO private pilot forwarding'
 if marker not in old.get('options',''):
  options=old.get('options','')+'\nMatch all\n'+marker+'\nMatch User '+cfg['user']+'\n    AllowTcpForwarding local\n    PermitOpen 127.0.0.1:3010 127.0.0.1:54321 127.0.0.1:15432\nMatch all\n'
  print(n.python('OPTIONS='+repr(options)+'\n'+"from truenas_api_client import Client\nimport json\nwith Client() as c:\n c.call('ssh.update',{'options':OPTIONS})\n print(json.dumps({'private_forward_exception':True,'ports':[3010,54321,15432]}))"))
 else:print(json.dumps({'private_forward_exception':'already_configured'}))
finally:n.close()
