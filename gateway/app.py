from __future__ import annotations

import asyncio
import base64
from collections import deque
from contextlib import ExitStack, asynccontextmanager, contextmanager, suppress
from dataclasses import dataclass, field
import logging
import os
from pathlib import Path
import re
import secrets
import hashlib
from functools import partial
from time import perf_counter

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from hermes_bridge import HermesBrain, HermesUnavailable
from speech import LocalSpeech, RATE, MAX_SECONDS
from voice_service import VoiceService
from weather import WeatherService, grounding_message
from device_context import DeviceContext, pet_name, user_turn_message
from artifacts import ArtifactSigner, checked_id, file_manifest
from wake_jobs import WakeJobs
from turn_stream import StreamingTurn, speech_parts, prefetched_reply, owned_call
from prompt_history import PromptHistory
from clock_context import ClockService
from memory_store import Memory, ExchangeConflict
from fast_brain import FastBrain, ConversationBrain
from memory_review import MemoryReviewer
from navigation import Navigation, Providers, intent as navigation_intent
from navigation_api import routes as navigation_routes
from pydantic import field_validator

logger = logging.getLogger("uvicorn.error")


class DeliveredResponse(Response):
    """Record delivery after ASGI sends the complete legacy PCM response."""
    def __init__(self,*args,commit,interrupt,**kwargs):
        super().__init__(*args,**kwargs)
        self.commit,self.interrupt=commit,interrupt

    async def __call__(self,scope,receive,send):
        try:
            await super().__call__(scope,receive,send)
            self.commit()
        except BaseException:
            self.interrupt()
            raise


class TurnTiming:
    """Only numeric durations; never include conversation or location data."""
    def __init__(self):
        self.started = perf_counter()
        self.durations = {}
        self.request_gps = False

    @contextmanager
    def stage(self, name):
        start = perf_counter()
        try:
            yield
        finally:
            self.durations[name] = (perf_counter() - start) * 1000

    def finish(self):
        self.durations["total"] = (perf_counter() - self.started) * 1000
        return ", ".join(f"{name};dur={duration:.2f}" for name, duration in self.durations.items())


@dataclass
class Settings:
    token: str
    data_dir: Path
    voice_path: Path
    whisper_model: str = "base"
    hermes_url: str = "http://192.168.8.245:30432"
    hermes_key: str = ""
    hermes_profile: str = "mochi"
    voice_speaker: int = 1
    voice_pitch: float = 2.5
    voice_length_scale: float = 1.03
    voice_engine: str = "piper"
    voice_provider: str = "local"
    audio_cache_mb: int = 256
    wake_worker_enabled: bool = False
    native_voice_url: str = ''
    native_voice_token: str = ''
    native_voice_profile: str = ''
    native_voice_source: str = 'nas'
    elevenlabs_api_key: str = field(default='', repr=False)
    elevenlabs_voice_id: str = ''
    elevenlabs_model_id: str = 'eleven_flash_v2_5'
    elevenlabs_voice_revision: str = ''
    hermes_warmup: bool = False
    hermes_agent: bool = False
    timezone_name: str = 'Europe/Madrid'
    fast_enabled: bool = False
    fast_url: str = 'http://192.168.8.245:8776'
    fast_key: str = ''
    profile_dir: str = ''
    memory_review_enabled: bool = False
    memory_review_url: str = ''
    memory_path: str = ''
    navigation_enabled: bool = False
    navigation_photon: str = 'https://photon.komoot.io/api/'
    navigation_router: str = 'https://routing.openstreetmap.de'
    navigation_tiles: str = 'https://tile.openstreetmap.org'
    whisper_encoder_frames: int = 0

    @classmethod
    def from_env(cls):
        data = Path(os.getenv("MOCHI_DATA_DIR", "data")).resolve()
        return cls(token=os.getenv('MOCHI_TOKEN',''),data_dir=data,
            voice_path=Path(os.getenv('MOCHI_VOICE_PATH',str(data/'voices/es_ES-sharvard-medium.onnx'))),
            whisper_model=os.getenv('WHISPER_MODEL','base'),hermes_url=os.getenv('HERMES_URL','http://192.168.8.245:30432'),
            whisper_encoder_frames=int(os.getenv('WHISPER_ENCODER_FRAMES','0')),
            hermes_key=os.getenv('HERMES_API_KEY',''),hermes_profile=os.getenv('HERMES_PROFILE','mochi'),
            voice_speaker=int(os.getenv('MOCHI_VOICE_SPEAKER','1')),voice_pitch=float(os.getenv('MOCHI_VOICE_PITCH','2.5')),
            voice_length_scale=float(os.getenv('MOCHI_VOICE_LENGTH_SCALE','1.03')),
            voice_engine='piper',voice_provider=os.getenv('MOCHI_VOICE_PROVIDER','native'),
            audio_cache_mb=int(os.getenv('MOCHI_AUDIO_CACHE_MB','256')),
            wake_worker_enabled=os.getenv('MOCHI_WAKE_WORKER_ENABLED','0')=='1',
            native_voice_url=os.getenv('MOCHI_NATIVE_VOICE_URL',''),native_voice_token=os.getenv('MOCHI_NATIVE_VOICE_TOKEN',''),
            native_voice_profile=os.getenv('MOCHI_NATIVE_VOICE_PROFILE',''),native_voice_source=os.getenv('MOCHI_NATIVE_VOICE_SOURCE','nas'),
            elevenlabs_api_key=(Path(os.environ['ELEVENLABS_API_KEY_FILE']).read_text(encoding='utf-8').strip()
                if os.getenv('ELEVENLABS_API_KEY_FILE') else os.getenv('ELEVENLABS_API_KEY','')),
            elevenlabs_voice_id=os.getenv('ELEVENLABS_VOICE_ID',''),
            elevenlabs_model_id=os.getenv('ELEVENLABS_MODEL_ID','eleven_flash_v2_5'),
            elevenlabs_voice_revision=os.getenv('ELEVENLABS_VOICE_REVISION',''),
            hermes_warmup=os.getenv('MOCHI_HERMES_WARMUP','0')=='1',hermes_agent=os.getenv('MOCHI_AGENT_ENABLED','1')=='1',
            timezone_name=os.getenv('MOCHI_TIMEZONE','Europe/Madrid'),fast_enabled=os.getenv('MOCHI_FAST_ENABLED','0')=='1',
            fast_url=os.getenv('MOCHI_FAST_URL','http://192.168.8.245:8776'),fast_key=os.getenv('MOCHI_FAST_KEY',''),
            profile_dir=os.getenv('MOCHI_PROFILE_DIR',''),memory_review_enabled=os.getenv('MOCHI_MEMORY_REVIEW_ENABLED','0')=='1',
            memory_review_url=os.getenv('MOCHI_MEMORY_REVIEW_URL',''),
            memory_path=os.getenv('MOCHI_MEMORY_PATH',''), navigation_enabled=os.getenv('MOCHI_NAVIGATION_ENABLED','0')=='1',
            navigation_photon=os.getenv('MOCHI_NAVIGATION_PHOTON','https://photon.komoot.io/api/'),
            navigation_router=os.getenv('MOCHI_NAVIGATION_ROUTER','https://routing.openstreetmap.de'),
            navigation_tiles=os.getenv('MOCHI_NAVIGATION_TILES','https://tile.openstreetmap.org'))

    def local_speech(self) -> LocalSpeech:
        return LocalSpeech(self.voice_path,self.whisper_model,self.data_dir/'models',
            self.voice_speaker,self.voice_pitch,self.voice_length_scale,
            encoder_frames=self.whisper_encoder_frames)



class LocationInput(BaseModel):
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    age_seconds: int = Field(default=0, ge=0, le=86400)
    current: bool = True


class ChatInput(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    device_id: str = Field(default="mochi", pattern=r"^[A-Za-z0-9_-]{1,48}$")
    location: LocationInput | None = None
    exchange_id: str | None = Field(default=None, pattern=r'^[A-Za-z0-9_-]{1,96}$')


class SayInput(BaseModel):
    text: str = Field(min_length=1, max_length=240)


class WakeJobInput(BaseModel):
    name: str
    device_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,48}$")
    _name = field_validator("name")(pet_name)


def create_app(settings: Settings, brain=None, speech=None, weather=None, clock=None, navigation=None):
    if len(settings.token) < 32:
        raise RuntimeError("MOCHI_TOKEN must contain at least 32 characters")
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    if settings.voice_provider not in {"local", "native", "elevenlabs"}:
        raise RuntimeError("Invalid voice provider or cache policy")
    brain = brain or HermesBrain(settings.hermes_url, settings.hermes_key, settings.hermes_profile,
                                agent_mode=settings.hermes_agent)
    if settings.fast_enabled:
        brain = ConversationBrain(brain, FastBrain(settings.fast_url, settings.fast_key, settings.profile_dir))
    speech = VoiceService(settings, speech or settings.local_speech())
    memory = Memory(Path(settings.memory_path) if settings.memory_path else settings.data_dir / "memory.sqlite3", recover=True)
    prompt_history=PromptHistory()
    jobs = WakeJobs(settings.data_dir / "wake-models")
    signer = ArtifactSigner(settings.data_dir / "artifact-signing-key.pem")
    lock = asyncio.Lock()
    # A background extraction with a different system prompt must not evict
    # the conversation prefix from the single fast-model slot.
    reviewer = MemoryReviewer(memory,settings.memory_review_url or settings.fast_url,settings.fast_key) if settings.memory_review_enabled else None
    if reviewer: reviewer.busy = lock.locked
    latency_samples = deque(maxlen=64)
    weather = weather or WeatherService()
    clock = clock or ClockService(settings.timezone_name)
    navigation = (navigation or Navigation(settings.data_dir, Providers(settings.data_dir,
        photon=settings.navigation_photon, router=settings.navigation_router, tiles=settings.navigation_tiles))) if settings.navigation_enabled else None
    @asynccontextmanager
    async def lifespan(application):
        # Register cleanup before warmup so failed starts also close HTTP pools.
        with ExitStack() as resources:
            for service in (brain, speech, weather, navigation):
                close = getattr(service, 'close', None)
                if callable(close): resources.callback(close)
            try:
                start = perf_counter()
                # Keep the loaded objects in the serving process, before the first turn.
                await asyncio.to_thread(speech.warmup)
                if settings.hermes_warmup:
                    try:
                        with jobs.foreground():
                            await asyncio.to_thread(brain.warmup)
                    except HermesUnavailable:
                        # Model trouble must not prevent health checks and signed OTA.
                        # Conversation requests still validate the real final response.
                        logger.warning('Mochi model prewarm unavailable; gateway recovery endpoints remain available')
                application.state.speech_ready = True
                logger.info("Mochi speech models ready startup_ms=%.2f", (perf_counter() - start) * 1000)
                if reviewer: reviewer.start()
                yield
            finally:
                application.state.speech_ready = False
                if reviewer: await reviewer.stop()

    application = FastAPI(title="Mochi Gateway", version="0.4.0", docs_url=None, redoc_url=None,
                          openapi_url=None, lifespan=lifespan)
    application.state.speech_ready = False

    @application.middleware("http")
    async def time_conversation(request: Request, call_next):
        path = request.url.path
        if path not in {"/v1/turn", "/v1/chat", "/v1/say"}:
            return await call_next(request)
        timing = request.state.timing = TurnTiming()
        if reviewer and secrets.compare_digest(request.headers.get('authorization','').encode(), ('Bearer '+settings.token).encode()):
            async with reviewer.foreground(): response = await call_next(request)
        else: response = await call_next(request)
        response.headers["Server-Timing"] = timing.finish()
        if hasattr(timing,'exchange_id'): response.headers['X-Mochi-Turn-ID']=timing.exchange_id
        if hasattr(timing,'brain_route'): response.headers['X-Mochi-Route']=timing.brain_route
        if getattr(timing,'navigation_id',None): response.headers['X-Mochi-Navigation']=timing.navigation_id
        latency_samples.append({"route": path, "status": response.status_code,
            "brain_route": getattr(timing, 'brain_route', None),
            "phase": "first_pcm_ready" if response.headers.get("X-Mochi-Stream") == "pcm16" else
                     "reply_ready" if path == "/v1/chat" else "complete_audio_ready",
            "stages_ms": {name: round(duration, 2) for name, duration in timing.durations.items()}})
        logger.info("Mochi latency route=%s status=%d %s", path, response.status_code,
                    " ".join(f"{name}_ms={duration:.2f}" for name, duration in timing.durations.items()))
        return response

    def authenticate(authorization: str = Header(default="")):
        expected = "Bearer " + settings.token
        if not secrets.compare_digest(authorization.encode(), expected.encode()):
            raise HTTPException(401, "device_auth_required")

    if navigation: application.include_router(navigation_routes(navigation, authenticate, speech))

    @application.get("/v1/diagnostics/latency", dependencies=[Depends(authenticate)])
    async def latency_diagnostics():
        # In-memory numeric timings only. Never retain request bodies, device
        # identifiers, transcripts, location, audio or authentication headers.
        return {"capacity": 64, "samples": list(latency_samples)}

    def location_headers(x_mochi_latitude: float | None = Header(default=None),
                         x_mochi_longitude: float | None = Header(default=None),
                         x_mochi_location_age: int = Header(default=0, ge=0, le=86400),
                         x_mochi_location_current: int = Header(default=1, ge=0, le=1)):
        if x_mochi_latitude is None and x_mochi_longitude is None: return None
        try:
            return LocationInput(latitude=x_mochi_latitude, longitude=x_mochi_longitude,
                age_seconds=x_mochi_location_age, current=bool(x_mochi_location_current))
        except ValueError as exc:
            raise HTTPException(422, "invalid_gps_location") from exc

    def conversation(device: str, text: str, voice: bool, timing: TurnTiming, location=None, device_context=None, persist=True, prefetch=False, render=None, exchange_id=None, request_hash=None):
        render=render or speech.speak
        if device_context:
            text = device_context.question(text)
        text = text.strip()
        if not text:
            raise HTTPException(422, "no_speech_detected")
        pcm = None
        try: row = memory.begin(device,text,exchange_id,request_hash)
        except ExchangeConflict as exc: raise HTTPException(409,'exchange_id_reused') from exc
        timing.exchange_id = row['id']
        if navigation: timing.navigation_id = navigation.for_exchange(device, row['id'])
        if row['answer']:
            answer={'text':row['answer'],'emotion':row['emotion']}
            timing.brain_route=row['route']
            if voice: pcm=render(answer['text'])
            if getattr(timing,'navigation_id',None): timing.request_gps=True
            return answer,pcm
        if row['delivery']!='received': raise HTTPException(409,'exchange_outcome_unknown')
        try:
            with timing.stage("context"):
                history = memory.history(device)
                command = navigation_intent(text) if navigation else None
                nav_answer = None
                if command:
                    if command[0] == 'cancel':
                        navigation.cancel(device)
                        nav_answer = {'text':'He terminado la navegación.', 'emotion':'idle'}
                    else:
                        timing.navigation_id = navigation.start(device, command[1], row['id'], location)
                        timing.request_gps = True
                        nav_answer = {'text':'Elige en la pantalla si vas a pie o en coche.', 'emotion':'idle'}
                local_answer=nav_answer or (device_context.answer(text) if device_context else None) or clock.answer(
                    text,device_context.name if device_context else 'Mochi')
                context = None if local_answer else weather.context(text, location, history)
                timing.request_gps = timing.request_gps or bool(context and context['status']=='gps_waiting')
                messages=prompt_history.for_turn(device,history)+[user_turn_message(text,device_context,
                    grounding_message(context) if context and context['status']=='ready' else None,
                    clock.context(text) if not context else None)]
                if settings.fast_enabled:
                    # Keep the stable personality prefix small. Dynamic shared
                    # recall belongs in the current turn, for both routes.
                    import json
                    current=dict(messages[-1])
                    try: envelope=json.loads(current['content'])
                    except ValueError: envelope={'question':current['content']}
                    if not isinstance(envelope,dict):envelope={'question':current['content']}
                    envelope['mochi_exchange']={'id':row['id'],'device':device}
                    envelope['shared_memory']=memory.context(device,text)
                    current['content']=json.dumps(envelope,ensure_ascii=False,separators=(',',':'))
                    messages=prompt_history.for_fast_turn(device,history,current)
            if local_answer:
                answer=local_answer
            elif context and context["status"] != "ready":
                notices = {
                    "gps_waiting":"El GPS aún está buscando mi posición. Acércame a una ventana y lo intento de nuevo.",
                    "place_not_found":"No he encontrado ese lugar para consultar el tiempo.",
                    "unavailable":"Ahora no consigo consultar la previsión del tiempo. Lo intentamos en un ratito."
                }
                answer = {"text":notices[context["status"]],"emotion":"curious"}
            else:
                if prefetch and callable(getattr(brain,'reply_streaming',None)):
                    answer,pcm=prefetched_reply(brain,messages,render,timing)
                else:
                    with timing.stage("hermes"):
                        answer = brain.reply(messages)
            prompt_history.propose(device,history,messages,text,answer)
            timing.brain_route = 'local' if local_answer or (context and context['status']!='ready') else getattr(brain,'last_route','hermes')
            with timing.stage('memory'):
                memory.answered(row['id'],answer,timing.brain_route)
                if command: memory.review_commit([row], [])
            if voice:
                with timing.stage("tts"):
                    pcm = render(answer["text"])
            if voice and (not pcm or len(pcm) % 2 or len(pcm) > RATE * 2 * MAX_SECONDS):
                raise HTTPException(503, "invalid_voice_response")
        except HermesUnavailable as exc:
            memory.interrupt(row['id'])
            raise HTTPException(503, "hermes_mochi_unavailable") from exc
        except HTTPException:
            memory.interrupt(row['id'])
            raise
        except Exception as exc:
            memory.interrupt(row['id'])
            raise HTTPException(503, "voice_service_unavailable") from exc
        if persist:
            with timing.stage("memory"):
                memory.delivered(row['id'])
        return answer, pcm

    async def progressive_response(text, headers, commit, release, request, first_pcm=None, render=None):
        render=render or speech.speak
        parts = speech_parts(text)
        async def disconnected():
            # The upload has been consumed. Wait for a real ASGI disconnect;
            # nonblocking Request.is_disconnected() can miss it behind the
            # middleware's receive channel and its cancellation checkpoint.
            while True:
                message = await request.receive()
                if message['type'] == 'http.disconnect': return True
        watcher = asyncio.create_task(disconnected())
        try:
            try:
                await asyncio.sleep(0)
                if watcher.done() and watcher.result():
                    raise HTTPException(499, 'turn_cancelled')
                if first_pcm is None:
                    with request.state.timing.stage('tts_first'):
                        first = await owned_call(render, parts[0])
                else:first=first_pcm
            finally:
                if not watcher.done(): watcher.cancel()
                with suppress(asyncio.CancelledError): await watcher
            if not watcher.cancelled() and watcher.result():
                raise HTTPException(499, 'turn_cancelled')
            return StreamingTurn(first, parts[1:], render, commit, release, headers)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(503, 'voice_service_unavailable') from exc

    @application.get("/health", dependencies=[Depends(authenticate)])
    async def health():
        native_status=await asyncio.to_thread(speech.remote.status) if speech.remote else None
        return {"provider": "hermes", "profile": settings.hermes_profile,
                "profile_ready": await asyncio.to_thread(brain.ready),
                "sample_rate": RATE, "voice_engine": settings.elevenlabs_model_id if speech.elevenlabs else 'chatterbox' if speech.native else settings.voice_engine,
                "voice_provider": settings.voice_provider, "audio_cache": await asyncio.to_thread(speech.cache.stats),
                "voice_location": 'elevenlabs' if speech.elevenlabs else settings.native_voice_source if speech.native else 'nas',
                "speech_loaded": application.state.speech_ready,
                "wake_worker_enabled": settings.wake_worker_enabled,
                "fast_conversation_enabled": settings.fast_enabled,
                "shared_memory_review_enabled": settings.memory_review_enabled,
                "navigation_enabled": settings.navigation_enabled,
                "voice_installed": native_status.get('ready') if native_status is not None else
                    settings.voice_path.is_file(),
                "native_voice_profile": settings.native_voice_profile if speech.native else None,
                "elevenlabs_voice_id": settings.elevenlabs_voice_id if speech.elevenlabs else None,
                "voice_generation_available": native_status.get('generation_available') if native_status else None,
                "voice_quota_retry_seconds": native_status.get('quota_retry_seconds',0) if native_status else 0}

    @application.post("/v1/chat", dependencies=[Depends(authenticate)])
    async def chat(body: ChatInput, request: Request):
        if lock.locked():
            raise HTTPException(429, "mochi_busy")
        async with lock:
            with jobs.foreground():
                existing=memory.get(body.exchange_id) if body.exchange_id else None
                if existing and not existing['answer']:
                    raise HTTPException(409,'exchange_outcome_unknown')
                answer, _ = await owned_call(conversation, body.device_id, body.text, False,
                    request.state.timing, body.location, persist=False, exchange_id=body.exchange_id)
            identifier=request.state.timing.exchange_id
            return DeliveredResponse(JSONResponse(answer).body,media_type='application/json',
                commit=lambda:memory.delivered(identifier),interrupt=lambda:memory.interrupt(identifier))

    @application.post("/v1/turn", dependencies=[Depends(authenticate)])
    async def turn(request: Request, x_device_id: str = Header(default="mochi"),
                   x_mochi_context: str | None = Header(default=None),
                   x_mochi_stream: str = Header(default=''), x_mochi_audio_cache: str=Header(default='use'),
                   x_mochi_turn_id: str | None = Header(default=None),
                   location=Depends(location_headers)):
        if x_mochi_audio_cache not in ('use','bypass'):raise HTTPException(422,'invalid_cache_mode')
        try: exchange_id=memory.checked_id(x_mochi_turn_id)
        except ValueError as exc: raise HTTPException(422,'invalid_exchange_id') from exc
        if x_mochi_audio_cache=='bypass' and not (settings.voice_provider in {'local','elevenlabs'} or
                (speech.native and settings.native_voice_source=='nas')):
            raise HTTPException(422,'uncached_diagnostics_require_nas')
        render=partial(speech.speak,use_cache=False) if x_mochi_audio_cache=='bypass' else speech.speak
        try:
            device_context = DeviceContext.from_header(x_mochi_context)
        except ValueError as exc:
            raise HTTPException(422, "invalid_device_context") from exc
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,48}", x_device_id):
            raise HTTPException(400, "invalid_device_id")
        if request.headers.get("content-type", "").split(";")[0] != "application/octet-stream":
            raise HTTPException(415, "expected_pcm16_mono_16000")
        if lock.locked():
            raise HTTPException(429, "mochi_busy")
        await lock.acquire()
        foreground = jobs.foreground()
        entered = transferred = released = False
        def release():
            nonlocal released
            if not released:
                released = True
                try:
                    if entered: foreground.__exit__(None, None, None)
                finally:
                    memory.interrupt(exchange_id)
                    if reviewer: reviewer.last_activity=__import__('time').monotonic()
                    lock.release()
        try:
            foreground.__enter__()
            entered = True
            data = bytearray()
            with request.state.timing.stage("upload"):
                async for chunk in request.stream():
                    if len(data) + len(chunk) > RATE * 2 * 8:
                        raise HTTPException(413, "recording_too_long")
                    data.extend(chunk)
            if len(data) < RATE // 5 or len(data) % 2:
                raise HTTPException(422, "invalid_recording")
            request_hash=hashlib.sha256(bytes(data)+(x_mochi_context or '').encode()+str(location).encode()).hexdigest()
            existing=memory.get(exchange_id)
            if existing and (existing['device']!=x_device_id or existing['request_hash']!=request_hash):
                raise HTTPException(409,'exchange_id_reused')
            if existing and not existing['answer']:
                raise HTTPException(409,'exchange_outcome_unknown')
            try:
                with request.state.timing.stage("asr"):
                    text = existing['question'] if existing else await owned_call(speech.transcribe, bytes(data))
            except Exception as exc:
                raise HTTPException(503, "transcription_unavailable") from exc
            progressive = x_mochi_stream == 'pcm16'
            answer, pcm = await owned_call(conversation, x_device_id, text, not progressive,
                                                  request.state.timing, location, device_context, False, progressive, render,
                                                  exchange_id,request_hash)
            headers = {"X-Mochi-Emotion": answer["emotion"], "X-Mochi-Sample-Rate": str(RATE),
                "X-Mochi-Request-GPS": "1" if request.state.timing.request_gps else "0", "Cache-Control": "no-store",
                "X-Mochi-Audio-Cache":x_mochi_audio_cache}
            if progressive:
                response = await progressive_response(answer['text'], headers,
                    lambda: memory.delivered(exchange_id), release, request, pcm, render)
                transferred = True
                return response
            return DeliveredResponse(pcm, media_type="application/octet-stream", headers=headers,
                commit=lambda:memory.delivered(exchange_id),interrupt=lambda:memory.interrupt(exchange_id))
        finally:
            if not transferred: release()

    @application.get("/v1/weather", dependencies=[Depends(authenticate)])
    async def forecast(location=Depends(location_headers)):
        context = await asyncio.to_thread(weather.context, "¿Qué tiempo hace hoy?", location)
        return {"ready":context["status"] == "ready", **context}

    @application.post("/v1/say", dependencies=[Depends(authenticate)])
    async def say(body: SayInput, request: Request, x_mochi_stream: str = Header(default='')):
        if lock.locked():
            raise HTTPException(429, "mochi_busy")
        if not body.text.strip():
            raise HTTPException(422, "empty_text")
        if x_mochi_stream == 'pcm16':
            await lock.acquire()
            foreground = jobs.foreground()
            entered = transferred = released = False
            def release():
                nonlocal released
                if not released:
                    released = True
                    try:
                        if entered: foreground.__exit__(None, None, None)
                    finally: lock.release()
            try:
                foreground.__enter__()
                entered = True
                response = await progressive_response(body.text.strip(), {'X-Mochi-Sample-Rate': str(RATE)},
                    lambda: None, release, request)
                transferred = True
                return response
            finally:
                if not transferred: release()
        async with lock:
            with jobs.foreground():
                try:
                    with request.state.timing.stage("tts"):
                        pcm = await owned_call(speech.speak, body.text.strip())
                except Exception as exc:
                    raise HTTPException(503, "voice_service_unavailable") from exc
                if not pcm or len(pcm) % 2 or len(pcm) > RATE * 2 * MAX_SECONDS:
                    raise HTTPException(503, "invalid_voice_response")
                return Response(pcm, media_type="application/octet-stream", headers={
                    "X-Mochi-Sample-Rate": str(RATE), "Cache-Control": "no-store"})

    @application.post("/v1/wake-model/jobs", dependencies=[Depends(authenticate)], status_code=202)
    async def prepare_name(body: WakeJobInput):
        if not settings.wake_worker_enabled:
            raise HTTPException(503, "wake_worker_unavailable")
        try:
            return await asyncio.to_thread(jobs.create, body.name, body.device_id)
        except RuntimeError as exc:
            raise HTTPException(409, "name_preparation_pending") from exc

    @application.get("/v1/wake-model/jobs/{identifier}", dependencies=[Depends(authenticate)])
    async def preparation_status(identifier: str):
        try:
            checked_id(identifier)
        except ValueError as exc:
            raise HTTPException(404, "unknown_preparation") from exc
        job = await asyncio.to_thread(jobs.get, identifier)
        if not job:
            raise HTTPException(404, "unknown_preparation")
        report_path=jobs.directory(identifier)/'report.json'
        if job['stage'] in {'failed','ready'} and report_path.is_file():
            import json
            try:
                report=json.loads(report_path.read_text())
                job['validation']={key:report[key] for key in ('recall','negative_false_accepts',
                    'positive_clips','negative_clips','physical_test_required') if key in report}
            except (OSError,ValueError): pass
        return job

    def ready_model(identifier):
        try:
            checked_id(identifier)
        except ValueError as exc:
            raise HTTPException(404, "unknown_model") from exc
        job = jobs.get(identifier)
        path = jobs.directory(identifier) / "model.tflite"
        report_path = jobs.directory(identifier) / "report.json"
        if not job or job['stage'] != 'ready' or not path.is_file() or not report_path.is_file():
            raise HTTPException(404, "model_not_ready")
        import json
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if report.get("passed") is not True:
            raise HTTPException(409, "model_not_validated")
        return job, path, report

    @application.get("/v1/wake-models/{identifier}/manifest", dependencies=[Depends(authenticate)])
    async def model_manifest(identifier: str):
        job, path, report = await asyncio.to_thread(ready_model, identifier)
        payload = await asyncio.to_thread(file_manifest, path, kind="wake-model", version=identifier,
            name=job['name'], frontend="microfrontend-v1", sample_rate=16000,
            probability_cutoff=report['probability_cutoff'], sliding_window=report.get('sliding_window',5),
            arena_bytes=report.get('arena_bytes',262144), physical_test_required=True)
        return signer.sign(payload)

    @application.get("/v1/wake-models/{identifier}/model", dependencies=[Depends(authenticate)])
    async def download_model(identifier: str):
        _, path, _ = await asyncio.to_thread(ready_model, identifier)
        return FileResponse(path, media_type="application/octet-stream", headers={"Cache-Control":"no-store"})

    @application.get("/v1/artifacts/public-key", dependencies=[Depends(authenticate)])
    async def public_key():
        return {"algorithm":"ecdsa-p256-sha256", "der":base64.b64encode(signer.public_key()).decode()}

    @application.get("/v1/updates/manifest", dependencies=[Depends(authenticate)])
    async def update_manifest():
        import json
        path = settings.data_dir / "updates/manifest.json"
        if not path.is_file():
            raise HTTPException(404, "no_update_available")
        # Publisher writes an already-signed manifest; serving never signs arbitrary uploads.
        from artifacts import verify_manifest
        envelope = json.loads(path.read_text(encoding="utf-8"))
        payload = verify_manifest(envelope, signer.public_key())
        if payload.get('kind') != 'firmware':
            raise HTTPException(503, "invalid_update")
        return envelope

    @application.get("/v1/updates/firmware", dependencies=[Depends(authenticate)])
    async def download_update():
        await update_manifest()
        path = settings.data_dir / "updates/firmware.bin"
        if not path.is_file():
            raise HTTPException(404, "no_update_available")
        return FileResponse(path,media_type="application/octet-stream",headers={"Cache-Control":"no-store"})

    application.state.jobs = jobs
    application.state.signer = signer
    application.state.memory = memory
    application.state.voice = speech
    return application


def app_factory():
    return create_app(Settings.from_env())
