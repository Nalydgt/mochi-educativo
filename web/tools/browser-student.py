import subprocess,json,base64,shutil
from pathlib import Path
root=Path(__file__).resolve().parents[1]
demo=json.loads((root/'.runtime/demo-login.json').read_text())
pupil=next(x for x in demo['pupils'] if x['name']=='Luna')
script='''(()=>{const input=document.querySelector('input[name="code"]');if(!input)throw new Error('Student form is not open');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,CODE);input.dispatchEvent(new Event('input',{bubbles:true}));input.form.requestSubmit();return 'Submitted individual classroom code';})()'''.replace('CODE',json.dumps(pupil['code']))
r=subprocess.run([shutil.which('agent-browser.cmd'),'--session','peluqo-alumno','eval','-b',base64.b64encode(script.encode()).decode()],text=True,capture_output=True,timeout=30)
print((r.stdout+r.stderr).replace(pupil['code'],'[private]'));raise SystemExit(r.returncode)
