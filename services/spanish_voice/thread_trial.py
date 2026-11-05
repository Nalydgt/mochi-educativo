"""Isolated CPU/PCM parity experiment; never used by the serving process.

Run with the active read-only assets mounted and no competing inference.
The output contains synthetic-test timings and hashes, never private audio.
"""
import ctypes
import gc
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import time

os.environ.setdefault('PKUSEG_HOME','/runtime/pkuseg')

import numpy as np
from scipy.signal import resample_poly
import torch
from chatterbox.mtl_tts import ChatterboxMultilingualTTS
from chatterbox.models.s3gen import S3Gen
from chatterbox.models.t3.modules.t3_config import T3Config
from chatterbox.models.tokenizers import MTLTokenizer
from chatterbox.models.voice_encoder import VoiceEncoder
from hybrid_assets import install

ROOT=Path(os.getenv('MOCHI_NATIVE_ASSETS','/assets'))
OUTPUT=Path(os.getenv('MOCHI_THREAD_TRIAL_OUTPUT','/fast/thread-trial-report.json'))
TEXT='Puedo ayudarte con eso.'
REFERENCE_HASH='b22a4d3f88efbe37e697186e43012129c405648ec04c2d530cc897a35173097d'


def rss():
    return int(Path('/proc/self/statm').read_text().split()[1])*os.sysconf('SC_PAGE_SIZE')


def trim():
    before=rss();gc.collect()
    function=ctypes.CDLL(None).malloc_trim
    function.argtypes=[ctypes.c_size_t];function.restype=ctypes.c_int
    function(0)
    return {'before_bytes':before,'after_bytes':rss()}


def pcm(waveform,sample_rate):
    data=resample_poly(waveform.detach().cpu().numpy().reshape(-1),16000,sample_rate)
    if not np.isfinite(data).all() or not 0<len(data)<=45*16000:
        raise ValueError('Invalid synthetic-test audio')
    return np.clip(np.rint(data*32768),-32768,32767).astype('<i2').tobytes()


def describe(data,reference=None):
    result={'pcm_sha256':hashlib.sha256(data).hexdigest(),'audio_seconds':len(data)/32000,
            'matches_production_pcm':hashlib.sha256(data).hexdigest()==REFERENCE_HASH}
    if reference is not None:
        a=np.frombuffer(data,dtype='<i2').astype(np.float64)
        b=np.frombuffer(reference,dtype='<i2').astype(np.float64)
        result['same_samples']=len(a)==len(b)
        if len(a)==len(b):
            result['pcm16_max_delta']=float(np.max(np.abs(a-b)))
            result['waveform_cosine']=float(np.dot(a,b)/(np.linalg.norm(a)*np.linalg.norm(b)))
    return result


def main():
    torch.set_num_threads(4);torch.set_num_interop_threads(1);torch.set_flush_denormal(True)
    profile=json.loads((ROOT/'profile.json').read_text())
    identifier=hashlib.sha256(json.dumps(profile,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
    if profile.get('backend')!='ggml-t3-torch-decoder' or profile.get('decoder_cfm_steps')!=4:
        raise ValueError('This trial requires the approved four-step native voice')
    started=time.monotonic()
    # from_local would first allocate 2.1 GB of Torch T3 and discard it. The
    # approved native adapter only needs its config and prepared conditioning.
    ve=VoiceEncoder()
    ve.load_state_dict(torch.load(ROOT/'ve.pt',map_location='cpu',weights_only=True));ve.eval()
    decoder=S3Gen()
    decoder.load_state_dict(torch.load(ROOT/'s3gen.pt',map_location='cpu',weights_only=True));decoder.eval()
    tokenizer=MTLTokenizer(str(ROOT/'grapheme_mtl_merged_expanded_v1.json'))
    model=ChatterboxMultilingualTTS(SimpleNamespace(hp=T3Config.multilingual()),decoder,ve,tokenizer,'cpu')
    model.prepare_conditionals(str(ROOT/'reference.wav'),exaggeration=profile['exaggeration'])
    report={'profile':identifier,'synthetic_text':TEXT,'production_sha256':REFERENCE_HASH,
            'load_seconds':time.monotonic()-started,'t3':[],'decoder':[]}
    adapter=None;capture={};timings={}
    original_decoder=decoder.inference
    def decode(*args,**kwargs):
        kwargs={**kwargs,'n_cfm_timesteps':4}
        capture.update(args=args,kwargs=kwargs,rng=torch.get_rng_state())
        began=time.monotonic()
        try:return original_decoder(*args,**kwargs)
        finally:timings['decoder_seconds']=time.monotonic()-began
    decoder.inference=decode
    def generate():
        timings.clear();torch.manual_seed(profile['seed']);began=time.monotonic()
        with torch.inference_mode():
            audio=model.generate(TEXT,language_id='es',exaggeration=profile['exaggeration'],
                cfg_weight=profile['cfg_weight'],temperature=profile['temperature'])
        return pcm(audio,model.sr),time.monotonic()-began
    try:
        reference=None
        for threads in (8,2,4,8):
            if adapter is not None:adapter.close()
            active={**profile,'t3_threads':threads}
            adapter=install(model,ROOT,active,identifier,os.getenv('MOCHI_NATIVE_RUNTIME','/fast'))
            original_t3=adapter.inference
            def t3(*args,**kwargs):
                began=time.monotonic()
                try:return original_t3(*args,**kwargs)
                finally:timings['t3_seconds']=time.monotonic()-began
            adapter.inference=t3
            data,elapsed=generate()
            if reference is None:
                reference=data;report['initial_memory_trim']=trim()
            item={'threads':threads,'seconds':elapsed,'stages':dict(timings),**describe(data,reference)}
            report['t3'].append(item);print(json.dumps({'t3':item}),flush=True)
            OUTPUT.write_text(json.dumps(report,indent=2))
        # Reuse the same speech tokens and exact decoder RNG for all thread
        # choices; no T3 reruns or sampling drift can bias decoder comparisons.
        saved={**capture};decoder_reference=None
        for threads in (4,1,2,4,8):
            torch.set_num_threads(threads);torch.set_rng_state(saved['rng'])
            began=time.monotonic()
            with torch.inference_mode():
                audio=original_decoder(*saved['args'],**saved['kwargs'])[0]
            elapsed=time.monotonic()-began
            data=pcm(audio,model.sr)
            if decoder_reference is None:decoder_reference=data
            item={'threads':threads,'seconds':elapsed,**describe(data,decoder_reference)}
            report['decoder'].append(item);print(json.dumps({'decoder':item}),flush=True)
            OUTPUT.write_text(json.dumps(report,indent=2))
        # Test whether reference-only modules can be released while retaining
        # the device property S3Gen derives from tokenizer.parameters().
        class DeviceAnchor(torch.nn.Module):
            def __init__(self):
                super().__init__();self.register_parameter('anchor',torch.nn.Parameter(torch.zeros(1),requires_grad=False))
        before=rss()
        decoder.tokenizer=DeviceAnchor();decoder.speaker_encoder=None;model.ve=None;ve=None
        report['reference_module_trim']={'rss_before_bytes':before,**trim()}
        torch.set_num_threads(4)
        data,elapsed=generate()
        report['without_reference_modules']={'seconds':elapsed,**describe(data,reference)}
        report['finished']=True
        OUTPUT.write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
    finally:
        if adapter is not None:adapter.close()


if __name__=='__main__':main()
