"""Compare diffusion step counts in isolation, preserving T3, RNG and watermark."""
import gc
import json
from pathlib import Path
import time

import numpy as np
from scipy.signal import resample_poly
import soundfile as sf
import torch
from chatterbox.mtl_tts import ChatterboxMultilingualTTS
from hybrid_t3 import HybridT3

root=Path('/assets');output=Path('/results/decoder-v1');output.mkdir(exist_ok=True)
profile=json.loads((root/'profile.json').read_text())
torch.set_num_threads(8);torch.set_num_interop_threads(1);torch.set_flush_denormal(True)
model=ChatterboxMultilingualTTS.from_local(root,'cpu',t3_model=profile['checkpoint'])
model.prepare_conditionals(str(root/'reference.wav'),exaggeration=profile['exaggeration'])
adapter=HybridT3('/compile/cpp-v1/build/libmochi-t3.so','/compile/cpp-v1/t3-q8_0.gguf',
    model.conds.t3,model.t3.hp,seed=profile['seed'])
model.t3=adapter;gc.collect()

def clock():
    try:paused=json.loads(Path('/results/pauses.json').read_text())['seconds']
    except (OSError,ValueError,KeyError):paused=0
    return time.monotonic()-paused

original_t3=adapter.inference;original_decoder=model.s3gen.inference
cache={};times={};steps=10
def t3(**kwargs):
    key=tuple(kwargs['text_tokens'].reshape(-1).tolist())
    if key not in cache:
        began=clock();tokens=original_t3(**kwargs)
        cache[key]=(tokens.clone(),torch.get_rng_state(),clock()-began)
    tokens,rng,seconds=cache[key]
    torch.set_rng_state(rng);times['t3']=seconds
    return tokens.clone()
def decode(*args,**kwargs):
    began=clock()
    try:return original_decoder(*args,**{**kwargs,'n_cfm_timesteps':steps})
    finally:times['decoder']=clock()-began
adapter.inference=t3;model.s3gen.inference=decode

reports=[]
for index,text in enumerate(('Estoy feliz.','Me encuentro genial.','Vamos a jugar juntos.')):
    reference=None
    for steps in (10,8,6,4):
        torch.manual_seed(profile['seed'])
        wav=model.generate(text,language_id='es',exaggeration=profile['exaggeration'],
            cfg_weight=profile['cfg_weight'],temperature=profile['temperature'])
        data=wav.detach().cpu().numpy().reshape(-1)
        if not np.isfinite(data).all():raise ValueError('Invalid trial waveform')
        if reference is None:reference=data.copy()
        if len(data)!=len(reference):raise ValueError('Decoder changed the sample count')
        a=reference.astype(np.float64);b=data.astype(np.float64)
        cosine=float(np.dot(a,b)/(np.linalg.norm(a)*np.linalg.norm(b)))
        spectrum_a=np.abs(np.fft.rfft(a));spectrum_b=np.abs(np.fft.rfft(b))
        spectrum_cosine=float(np.dot(spectrum_a,spectrum_b)/(np.linalg.norm(spectrum_a)*np.linalg.norm(spectrum_b)))
        pcm=resample_poly(data,16000,model.sr)
        sf.write(output/f'{index}-{steps}.wav',np.clip(pcm,-1,1),16000,subtype='PCM_16')
        item={'index':index,'steps':steps,'estimated_uncached_seconds':round(sum(times.values()),3),
            't3_seconds':round(times['t3'],3),'decoder_seconds':round(times['decoder'],3),
            'audio_seconds':len(data)/model.sr,'waveform_cosine':cosine,'spectrum_cosine':spectrum_cosine,
            'rms_ratio':float(np.linalg.norm(b)/np.linalg.norm(a)),'production_changed':False}
        reports.append(item);(output/'report.json').write_text(json.dumps(reports,indent=2))
        print(json.dumps(item),flush=True)
adapter.close()
