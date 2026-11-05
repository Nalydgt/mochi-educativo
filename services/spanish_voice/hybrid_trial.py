"""Measure an isolated persistent T3; keep the approved Torch audio decoder."""
import gc
import json
from pathlib import Path
import time

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly
import torch
from chatterbox.mtl_tts import ChatterboxMultilingualTTS
from hybrid_t3 import HybridT3

root=Path('/assets');output=Path('/results/hybrid-v1');output.mkdir(exist_ok=True)
profile=json.loads((root/'profile.json').read_text())
torch.set_num_threads(8);torch.set_num_interop_threads(1);torch.set_flush_denormal(True)
model=ChatterboxMultilingualTTS.from_local(root,'cpu',t3_model=profile['checkpoint'])
model.prepare_conditionals(str(root/'reference.wav'),exaggeration=profile['exaggeration'])
adapter=HybridT3('/compile/cpp-v1/build/libmochi-t3.so','/compile/cpp-v1/t3-q8_0.gguf',
    model.conds.t3,model.t3.hp,seed=profile['seed'])
from hybrid_parity import check
parity=check(model,adapter)
(output/'parity.json').write_text(json.dumps(parity,indent=2))
print(json.dumps({'parity':parity}),flush=True)
if not parity['passed']:raise RuntimeError('Native T3 numerical parity failed')
model.t3=adapter;gc.collect()

def clock():
    try:paused=json.loads(Path('/results/pauses.json').read_text())['seconds']
    except (OSError,ValueError,KeyError):paused=0
    return time.monotonic()-paused

reports=[]
timings={}
decoder_capture={}
for name,component in (('t3',adapter),('decoder',model.s3gen)):
    original=component.inference
    def measured(*args,_fn=original,_name=name,**kwargs):
        started=clock()
        if _name=='decoder':
            decoder_capture.update({'args':args,'kwargs':kwargs,'rng':torch.get_rng_state(),'fn':_fn})
        try:
            result=_fn(*args,**kwargs)
            if _name=='decoder':decoder_capture['reference']=result[0].detach().clone()
            return result
        finally:timings[_name]=round(clock()-started,3)
    component.inference=measured
for index,text in enumerate(('Estoy feliz.','Me encuentro genial.','Vamos a jugar juntos.',profile['approved_text'])):
    torch.manual_seed(profile['seed']);started=clock()
    wav=model.generate(text,language_id='es',exaggeration=profile['exaggeration'],
        cfg_weight=profile['cfg_weight'],temperature=profile['temperature'])
    elapsed=clock()-started
    data=resample_poly(wav.detach().cpu().numpy().reshape(-1),16000,model.sr)
    if not np.isfinite(data).all() or not 0<len(data)<45*16000:raise ValueError('Invalid hybrid PCM')
    sf.write(output/(str(index)+'.wav'),np.clip(data,-1,1),16000,subtype='PCM_16')
    item={'index':index,'seconds':round(elapsed,3),'audio_seconds':len(data)/16000,
        'stages':dict(timings),'decoder':'original FP32 S3Gen','t3':'GGML Q8_0',
        'sampler':'original Torch','production_changed':False}
    reports.append(item);(output/'report.json').write_text(json.dumps(reports,indent=2))
    print(json.dumps(item),flush=True)
    if index==2:
        decoder_reports=[]
        for threads in (1,2,4,8):
            torch.set_num_threads(threads);torch.set_rng_state(decoder_capture['rng'])
            began=clock()
            result=decoder_capture['fn'](*decoder_capture['args'],**decoder_capture['kwargs'])[0]
            elapsed=clock()-began
            a=decoder_capture['reference'].reshape(-1).double()
            b=result.reshape(-1).double()
            cosine=float(torch.dot(a,b)/(torch.linalg.norm(a)*torch.linalg.norm(b)))
            decoder_reports.append({'threads':threads,'seconds':round(elapsed,3),'waveform_cosine':cosine})
        (output/'decoder-threads.json').write_text(json.dumps(decoder_reports,indent=2))
        eligible=[r for r in decoder_reports if r['waveform_cosine']>.9999]
        if not eligible:raise RuntimeError('No decoder thread count preserved the waveform')
        best=min(eligible,key=lambda row:row['seconds'])['threads']
        torch.set_num_threads(best)
        print(json.dumps({'decoder_threads':decoder_reports,'selected':best}),flush=True)
        decoder_capture.clear()
adapter.close()
# Importing the exporter publishes the verified assets after all parity checks.
import export_hybrid_artifacts  # noqa: F401
