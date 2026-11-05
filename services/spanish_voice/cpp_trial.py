"""Prepare the verified GGUF and conditioning assets used by the approved hybrid build."""
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np
import torch

ROOT=Path('/compile/cpp-v1')
SOURCE=ROOT/'source'
OUTPUT=Path('/results/cpp-v1')
ASSETS=Path('/assets')
profile=json.loads((ASSETS/'profile.json').read_text())
torch.set_num_threads(8)
torch.set_num_interop_threads(1)
torch.set_flush_denormal(True)

def call(arguments,log):
    with (OUTPUT/log).open('ab') as stream:
        subprocess.run(arguments,stdout=stream,stderr=stream,check=True)

# The upstream converter defaults to V2, with the same tensor architecture.
# Use the exact V3 checkpoint already verified by the production asset profile.
original=(SOURCE/'scripts/convert-t3-mtl-to-gguf.py').read_text()
patched=original.replace('t3_mtl23ls_v2.safetensors',profile['checkpoint'])
converter=SOURCE/'scripts/convert-mochi-v3.py'
converter.write_text(patched)
for filename in ('t3_mtl23ls_v3.safetensors','s3gen.pt','reference.wav'):
    expected=profile['files'][filename]
    with (ASSETS/filename).open('rb') as source:
        if hashlib.file_digest(source,'sha256').hexdigest()!=expected:
            raise RuntimeError('Production voice asset integrity mismatch')
for precision in ('f16','q8_0'):
    target=ROOT/('t3-'+precision+'.gguf')
    if not target.is_file():
        call(['/runtime/venv/bin/python',str(converter),'--ckpt-dir',str(ASSETS),
              '--quant',precision,'--out',str(target)],'convert-t3-'+precision+'.log')
s3=ROOT/'s3-f16.gguf'
if not s3.is_file():
    call(['/runtime/venv/bin/python',str(SOURCE/'scripts/convert-s3gen-to-gguf.py'),
          '--ckpt-dir',str(ASSETS),'--variant','mtl','--quant','f16','--out',str(s3)],'convert-s3.log')

voice=ROOT/'voice';voice.mkdir(exist_ok=True)
if not (voice/'speaker_emb.npy').is_file():
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    model=ChatterboxMultilingualTTS.from_local(ASSETS,'cpu',t3_model=profile['checkpoint'])
    model.prepare_conditionals(str(ASSETS/'reference.wav'),exaggeration=profile['exaggeration'])
    tensors={'speaker_emb':model.conds.t3.speaker_emb,
        'cond_prompt_speech_tokens':model.conds.t3.cond_prompt_speech_tokens,
        **{name:model.conds.gen[name] for name in ('embedding','prompt_token','prompt_feat')}}
    for name,tensor in tensors.items():
        data=tensor.detach().cpu().numpy()
        if name=='prompt_feat':data=data.reshape(-1,80)
        else:data=data.reshape(-1)
        dtype=np.int32 if name in ('prompt_token','cond_prompt_speech_tokens') else np.float32
        np.save(voice/(name+'.npy'),np.ascontiguousarray(data,dtype=dtype))
    del tensors,model
    import gc;gc.collect()
for path in voice.glob('*.npy'):
    dtype=np.int32 if path.stem in ('prompt_token','cond_prompt_speech_tokens') else np.float32
    np.save(path,np.ascontiguousarray(np.load(path),dtype=dtype))
