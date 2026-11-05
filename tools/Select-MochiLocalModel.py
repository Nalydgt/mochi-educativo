"""Select the validated NAS endpoint only for Hermes' Mochi profile."""
import base64
import argparse
import json
from pathlib import Path
from nas import NAS

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--conversation-only',action='store_true',help='Omit unused API tool guidance while retaining stored identity and memories')
parser.add_argument('--agent-tools',action='store_true',help='Enable configured web, memory, file, terminal and automation tools')
parser.add_argument('--context-length',type=int,choices=(16384,32768,65536),default=65536,
                    help='Declare the validated context supported by the local server')
args=parser.parse_args()
if args.agent_tools and args.conversation_only:parser.error('Choose agent tools or conversation-only mode')
key=(ROOT/'.runtime/mochi-local-model.key').read_text().strip()
if len(key)<32:raise ValueError('A private local model key is required')
source='TOKEN='+repr(key)+'\nCONVERSATION_ONLY='+repr(args.conversation_only)+'\nAGENT_TOOLS='+repr(args.agent_tools)+'\nCONTEXT_LENGTH='+repr(args.context_length)+'\n'+r'''
from pathlib import Path
import hashlib,json,os
import yaml
root=Path('/opt/data/profiles/mochi')
owner=root.stat()
path=root/'config.yaml'
before=path.read_bytes()
backup=root/'config.before-local-20261023.yaml'
if not backup.exists():
 backup.write_bytes(before);backup.chmod(0o600)
os.chown(backup,owner.st_uid,owner.st_gid)
if AGENT_TOOLS:
 agent_backup=root/'config.before-agent-20261024.yaml'
 if not agent_backup.exists():agent_backup.write_bytes(before);agent_backup.chmod(0o600)
 os.chown(agent_backup,owner.st_uid,owner.st_gid)
soul=root/'SOUL.md'
soul_before=hashlib.sha256(soul.read_bytes()).hexdigest()
config=yaml.safe_load(before)
config['model']={'provider':'custom','default':'mochi-local','base_url':'http://192.168.8.245:8770/v1',
 'api_key':TOKEN,'context_length':CONTEXT_LENGTH}
config['fallback_providers']=[]
config.pop('fallback_model',None)
platform_tools=config.setdefault('platform_toolsets',{})
if AGENT_TOOLS:
 platform_tools['api_server']=['web','memory','session_search','terminal','file','todo','cronjob','code_execution']
elif CONVERSATION_ONLY:platform_tools['api_server']=[]
else:platform_tools.setdefault('api_server',['memory','session_search'])
agent=config.setdefault('agent',{})
agent.update({'api_max_retries':0,'auto_recovery_cycles':0,'max_turns':8,'gateway_timeout':90})
if CONVERSATION_ONLY or AGENT_TOOLS:
 for option in ('task_completion_guidance','parallel_tool_call_guidance','tool_use_enforcement',
                'execution_guidance','environment_probe','bot_mode_protocol'):
  agent[option]=False
for task in config.get('auxiliary',{}).values():
 if isinstance(task,dict) and 'provider' in task:
  task['provider']='auto'
  task.pop('model',None);task.pop('base_url',None);task.pop('api_key',None)
if CONVERSATION_ONLY or AGENT_TOOLS:
 # Every stateless spoken API session otherwise launches a title model call.
 # It competes with TTS and evicts the single local model's conversation KV.
 config.setdefault('auxiliary',{}).setdefault('title_generation',{})['model_upgrade_enabled']=False
if AGENT_TOOLS:
 config.setdefault('display',{})['interim_assistant_messages']=False
temporary=path.with_suffix('.local-partial')
temporary.write_text(yaml.safe_dump(config,allow_unicode=True,sort_keys=False))
temporary.chmod(0o600);os.chown(temporary,owner.st_uid,owner.st_gid);temporary.replace(path)
assert hashlib.sha256(soul.read_bytes()).hexdigest()==soul_before
print(json.dumps({'profile':'mochi','provider':'custom','model':'mochi-local','inference':'NAS CPU',
 'fallback_providers':0,'soul_preserved':True,'memories_untouched':True,
 'conversation_only':CONVERSATION_ONLY,
 'agent_tools':AGENT_TOOLS,'enabled_toolsets':config['platform_toolsets']['api_server'],
 'model_generated_titles':config.get('auxiliary',{}).get('title_generation',{}).get('model_upgrade_enabled',True)}),flush=True)
'''
encoded=base64.b64encode(source.encode()).decode()
command="python - <<'PY'\nimport base64\nexec(base64.b64decode("+repr(encoded)+"))\nPY\n"
nas=NAS(json.loads((ROOT/'.runtime/nas.json').read_text(encoding='utf-8')))
try:print(nas.container('hermes-agent','hermes-agent',command,timeout=25))
finally:nas.close()
