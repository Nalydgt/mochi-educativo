"""Fill the visible teacher form without placing credentials in shell history."""
import subprocess,json,base64,shutil
from pathlib import Path
root=Path(__file__).resolve().parents[1]
s=json.loads((root/'.runtime/pilot-secrets.json').read_text())
values=json.dumps({'email':'docente@peluqo.local','password':s['teacher_password']})
script='''(()=>{const values=VALUES;for(const [name,value] of Object.entries(values)){const input=document.querySelector('input[name="'+name+'"]');if(!input)throw new Error('Teacher form is not open');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,value);input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new Event('change',{bubbles:true}));}document.querySelector('input[name="email"]').form.requestSubmit();return 'Submitted teacher form';})()'''.replace('VALUES',values)
browser=shutil.which('agent-browser.cmd')
r=subprocess.run([browser,'--session','peluqo','eval','-b',base64.b64encode(script.encode()).decode()],text=True,capture_output=True,timeout=30)
print((r.stdout+r.stderr).replace(s['teacher_password'],'[private]'));raise SystemExit(r.returncode)
