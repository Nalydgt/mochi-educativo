"""One preloaded local speaker: the user's chosen Spanish sample 03 recipe."""
from contextlib import asynccontextmanager
import ctypes
import gc
import hashlib
import json
import logging
import os
from pathlib import Path
import secrets
import threading
import time
import unicodedata
import wave

# Keep the tokenizer's auxiliary data across container recreation as well.
os.environ.setdefault('PKUSEG_HOME','/runtime/pkuseg')

from fastapi import Depends, FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, Field

ROOT=Path(os.environ.get('MOCHI_NATIVE_ASSETS','/assets'))
TOKEN=os.environ.get('MOCHI_NATIVE_TOKEN','')
DEVICE=os.environ.get('MOCHI_NATIVE_DEVICE','cpu')
if DEVICE not in {'cpu','cuda'}:raise RuntimeError('Unsupported voice execution device')
if len(TOKEN)<32: raise RuntimeError('A private service token is required')
logger=logging.getLogger('uvicorn.error')
generation_lock=threading.Lock()
model=None; profile=None; profile_id=None; approved_pcm=None
stage_ms={}


def digest(path):
    with path.open('rb') as source: return hashlib.file_digest(source,'sha256').hexdigest()


def normalize(text): return ' '.join(unicodedata.normalize('NFC',text).split())


def resident_bytes():
    try:
        return int(Path('/proc/self/statm').read_text().split()[1])*os.sysconf('SC_PAGE_SIZE')
    except (OSError,ValueError,IndexError,AttributeError):return None


def release_startup_allocations():
    """Return freed Torch load/warmup pages to the NAS, keeping live weights.

    Replacing the 2 GB Torch T3 releases its tensors, but glibc arenas can
    retain free pages. Returning them once before readiness leaves more RAM
    for ASR and the conversation model's mapped weights. Never trim during a
    turn: that would discard reusable scratch pages on the latency path.
    """
    before=resident_bytes()
    gc.collect()
    try:
        if os.name=='posix':
            trim=ctypes.CDLL(None).malloc_trim
            trim.argtypes=[ctypes.c_size_t];trim.restype=ctypes.c_int
            trim(0)
    except (AttributeError,OSError):pass  # Non-glibc platforms remain supported.
    after=resident_bytes()
    if before is not None and after is not None:
        logger.info('Speaker startup memory rss_before_bytes=%d rss_after_bytes=%d released_bytes=%d',
                    before,after,max(0,before-after))


def authenticate(authorization: str=Header(default='')):
    if not secrets.compare_digest(authorization.encode(),('Bearer '+TOKEN).encode()):
        raise HTTPException(401,'unauthorized')


def measure_stage(name,fn):
    # Generation is serialized by generation_lock (or runs before readiness).
    # Keep only durations, never text, speech tokens or waveform buffers.
    def measured(*args,**kwargs):
        started=time.monotonic()
        try:return fn(*args,**kwargs)
        finally:stage_ms[name]=(time.monotonic()-started)*1000
    return measured


def generate_pcm(text):
    import numpy as np
    import torch
    from scipy.signal import resample_poly
    stage_ms.clear()
    # This CPU mode is thread-local; FastAPI uses a request worker.
    torch.set_flush_denormal(True)
    # Startup warmup must not advance the approved request's sampler state.
    torch.manual_seed(profile['seed'])
    with torch.inference_mode():
        result=model.generate(text,language_id='es',exaggeration=profile['exaggeration'],
            cfg_weight=profile['cfg_weight'],temperature=profile['temperature'])
    data=result.detach().cpu().numpy().reshape(-1)
    if not np.isfinite(data).all() or not 0<len(data)<=model.sr*45:
        raise ValueError('Invalid synthesized audio')
    data=resample_poly(data,16000,model.sr)
    return np.clip(np.rint(data*32768),-32768,32767).astype('<i2').tobytes()


@asynccontextmanager
async def lifespan(application):
    global model,profile,profile_id,approved_pcm
    import torch
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    profile=json.loads((ROOT/'profile.json').read_text(encoding='utf-8'))
    profile_id=hashlib.sha256(json.dumps(profile,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
    if profile.get('schema')!=1 or profile.get('language')!='es': raise RuntimeError('Unsupported speaker profile')
    for filename,expected in profile['files'].items():
        if Path(filename).name!=filename or digest(ROOT/filename)!=expected:
            raise RuntimeError('Speaker asset integrity check failed')
    torch.set_num_threads(int(os.environ.get('OMP_NUM_THREADS','4')))
    torch.set_num_interop_threads(1)
    # Match the approved CPU benchmark. The two-phrase A/B check found
    # identical PCM16, without a measured speed improvement from this flag.
    torch.set_flush_denormal(True)
    torch.manual_seed(profile['seed'])
    started=time.monotonic()
    if DEVICE=='cuda' and not torch.cuda.is_available():raise RuntimeError('Configured GPU is unavailable')
    model=ChatterboxMultilingualTTS.from_local(ROOT,DEVICE,t3_model=profile['checkpoint'])
    model.prepare_conditionals(str(ROOT/'reference.wav'),exaggeration=profile['exaggeration'])
    adapter=None
    try:
        if profile.get('backend')=='ggml-t3-torch-decoder':
            if DEVICE!='cpu':raise RuntimeError('The optimized voice is validated only on the NAS CPU')
            from hybrid_assets import install
            adapter=install(model,ROOT,profile,profile_id,os.getenv('MOCHI_NATIVE_RUNTIME','/runtime'))
            torch.set_num_threads(profile['decoder_threads'])
            steps=profile.get('decoder_cfm_steps',10)
            if steps not in (4,6,8,10):raise RuntimeError('Unsupported decoder step count')
            if steps!=10:
                original_decoder=model.s3gen.inference
                def decode(*args,**kwargs):
                    return original_decoder(*args,**{**kwargs,'n_cfm_timesteps':steps})
                model.s3gen.inference=decode
        with wave.open(str(ROOT/'approved.wav'),'rb') as source:
            if (source.getnchannels(),source.getsampwidth(),source.getframerate())!=(1,2,16000):
                raise RuntimeError('Invalid approved sample format')
            approved_pcm=source.readframes(source.getnframes())
        model.t3.inference=measure_stage('t3',model.t3.inference)
        model.s3gen.inference=measure_stage('decoder',model.s3gen.inference)
        # Loading weights alone leaves lazy CPU kernels cold. Run real synthesis
        # before advertising readiness; discard it and never cache it as a reply.
        warmup_started=time.monotonic()
        generate_pcm('Estoy aquí.')
        warmup_ms=(time.monotonic()-warmup_started)*1000
        release_startup_allocations()
        logger.info('Speaker ready load_ms=%.1f warmup_ms=%.1f device=%s profile=%s',
            (warmup_started-started)*1000,warmup_ms,DEVICE,profile_id)
        stage_ms.clear()
        yield
    finally:
        if adapter is not None:adapter.close()
        model=None;approved_pcm=None;profile_id=None;profile=None
        stage_ms.clear()


app=FastAPI(title='Mochi Spanish voice',docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)


class SpeechInput(BaseModel):
    text: str=Field(min_length=1,max_length=1000)
    profile: str=Field(pattern=r'^[a-f0-9]{64}$')


@app.get('/health',dependencies=[Depends(authenticate)])
def health(): return {'ready':model is not None,'profile':profile_id,'sample_rate':16000,'language':'es','device':DEVICE}


@app.post('/v1/speech',dependencies=[Depends(authenticate)])
def speak(body: SpeechInput):
    if model is None: raise HTTPException(503,'voice_not_ready')
    if not secrets.compare_digest(body.profile,profile_id): raise HTTPException(409,'voice_profile_mismatch')
    text=normalize(body.text)
    if not text: raise HTTPException(422,'empty_text')
    if not generation_lock.acquire(blocking=False): raise HTTPException(429,'voice_busy')
    started=time.monotonic()
    try:
        stage_ms.clear()
        if text==normalize(profile['approved_text']): pcm=approved_pcm
        else:pcm=generate_pcm(text)
        elapsed=(time.monotonic()-started)*1000
        logger.info('Speech complete duration_ms=%.1f t3_ms=%.1f decoder_ms=%.1f bytes=%d',
            elapsed,stage_ms.get('t3',0),stage_ms.get('decoder',0),len(pcm))
        return Response(pcm,media_type='application/octet-stream',headers={
            'X-Mochi-Sample-Rate':'16000','X-Mochi-Voice-Profile':profile_id,
            'X-Mochi-TTS-Ms':f'{elapsed:.1f}',
            'Server-Timing':', '.join(f'{name};dur={value:.2f}' for name,value in stage_ms.items()),
            'Cache-Control':'no-store'})
    except Exception as failure:
        logger.error('Speech generation failed type=%s',type(failure).__name__)
        raise HTTPException(503,'speech_generation_failed') from None
    finally: generation_lock.release()
