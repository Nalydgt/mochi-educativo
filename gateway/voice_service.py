"""Selected NAS voice and persistent cache; no automatic change of timbre."""
import hashlib
from phrases import PHRASES
from voice_cache import AudioCache,clean_text,voice_key
from native_voice import NativeVoice
from elevenlabs_voice import ElevenLabsVoice
from navigation import CUES

class VoiceService:
    def __init__(self,settings,local):
        self.local,self.settings=local,settings
        self.cache=AudioCache(settings.data_dir/'audio-cache.sqlite3',settings.audio_cache_mb*1024*1024)
        resources={}
        if settings.voice_provider=='local':
            for path in (settings.voice_path,settings.voice_path.with_suffix(settings.voice_path.suffix+'.json')):
                if path.is_file():
                    with path.open('rb') as source:resources[path.name]=hashlib.file_digest(source,'sha256').hexdigest()
        self.local_id=voice_key({'provider':'piper','path':str(settings.voice_path),'resources':resources,
            'speaker':settings.voice_speaker,'pitch':settings.voice_pitch,'length':settings.voice_length_scale,
            'format':'pcm16-mono-16000-v1'})
        self.native=NativeVoice(settings.native_voice_url,settings.native_voice_token,settings.native_voice_profile) if settings.voice_provider=='native' else None
        self.native_id=voice_key({'provider':'native','profile':settings.native_voice_profile,'format':'pcm16-mono-16000-v1'}) if self.native else None
        self.elevenlabs=ElevenLabsVoice(settings.elevenlabs_api_key,settings.elevenlabs_voice_id,
            settings.elevenlabs_model_id,revision=settings.elevenlabs_voice_revision) if settings.voice_provider=='elevenlabs' else None
        self.remote=self.elevenlabs or self.native
        self.cache_id=self.elevenlabs.profile if self.elevenlabs else self.native_id if self.native else self.local_id
    def close(self):
        for voice in (self.native,self.elevenlabs):
            close = getattr(voice, 'close', None)
            if callable(close): close()
    def warmup(self):
        if self.remote and callable(getattr(self.local,'warmup_transcriber',None)):self.local.warmup_transcriber()
        else:self.local.warmup()
    def transcribe(self,pcm):return self.local.transcribe(pcm)
    def cached(self,text):
        return self.cache.get(self.cache_id,clean_text(text))
    def speak(self,text,*,use_cache=True):
        text=clean_text(text)
        generate=self.elevenlabs.generate if self.elevenlabs else self.native.generate if self.native else self.local.speak
        if not use_cache:
            if self.native and self.settings.native_voice_source!='nas':raise ValueError('Uncached diagnostics require the NAS speaker')
            return generate(text)
        return self.cache.render(self.cache_id,text,generate,text in PHRASES.values() or text in CUES.values())
