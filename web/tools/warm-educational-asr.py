import shlex
from pilot import NAS,settings
n=NAS(settings())
try:
 print('Preparing isolated speech recognition model',flush=True)
 code='''import app,json
from fastapi import HTTPException
try:app.transcribe(bytes(32000))
except HTTPException as e:
 if e.detail!='no_speech_detected':raise
print(json.dumps({'local_asr_model_loaded':app._asr is not None,'saved_recordings':0}))
'''
 print(n.container('peluqo-pilot','worker','/runtime/venv/bin/python -c '+shlex.quote(code),timeout=300),flush=True)
finally:n.close()
