from __future__ import annotations

import io
from contextlib import contextmanager
from pathlib import Path
import threading
import wave

import numpy as np

RATE = 16000
MAX_SECONDS = 45

def wav_to_pcm16(wav_data: bytes, pitch_semitones: float = 0) -> bytes:
    if not np.isfinite(pitch_semitones) or not -4 <= pitch_semitones <= 6:
        raise ValueError("Pitch must be between -4 and 6 semitones")
    pitch_ratio = 2 ** (pitch_semitones / 12)
    with wave.open(io.BytesIO(wav_data), "rb") as source:
        if source.getsampwidth() != 2 or source.getcomptype() != "NONE":
            raise ValueError("Expected uncompressed 16-bit WAV")
        channels, rate = source.getnchannels(), source.getframerate()
        if channels not in (1, 2) or rate < 8000 or source.getnframes() > rate * MAX_SECONDS * max(1, pitch_ratio):
            raise ValueError("Unsupported audio format or duration")
        pcm = np.frombuffer(source.readframes(source.getnframes()), dtype="<i2").astype(np.float32)
        if channels == 2:
            pcm = pcm.reshape(-1, 2).mean(axis=1)
        if len(pcm) == 0:
            raise ValueError("Empty synthesized audio")
        output_length = round(len(pcm) * RATE / (rate * pitch_ratio))
        if output_length < 1 or output_length > RATE * MAX_SECONDS:
            raise ValueError("Unsupported synthesized duration")
        if rate != RATE or pitch_semitones:
            pcm = np.interp(np.arange(output_length) * rate * pitch_ratio / RATE, np.arange(len(pcm)), pcm)
        return np.clip(pcm, -32768, 32767).astype("<i2").tobytes()


class LocalSpeech:
    def __init__(self, voice_path: Path, whisper_model: str = "base", model_dir: Path | None = None,
                 speaker_id: int = 1, pitch_semitones: float = 2.5, length_scale: float = 1.03,
                 engine: str = "piper", encoder_frames: int = 0):
        if engine != 'piper':raise ValueError('Unsupported diagnostic speech engine')
        if type(encoder_frames) is not int or encoder_frames not in (0,800,1600):
            raise ValueError('Encoder window must be 0, 800 or 1600 frames')
        self.voice_path,self.whisper_model,self.model_dir=voice_path,whisper_model,model_dir
        self.whisper=self.voice=None
        self.speaker_id,self.pitch_semitones,self.length_scale=speaker_id,pitch_semitones,length_scale
        self.engine=engine
        self.encoder_frames=encoder_frames
        self._encoder_state=threading.local()

    def installed(self):return self.voice_path.is_file()

    def warmup(self):
        self._load_voice()
        self.warmup_transcriber()

    def warmup_transcriber(self):
        self._load_transcriber()
        # Loading CTranslate2 weights does not initialize the decoder or Silero
        # VAD kernels. Exercise both before accepting the first microphone turn.
        # The signal is synthetic and discarded; no user's recording is kept.
        audio = np.zeros(RATE, dtype=np.float32)
        with self._encoder_window(self.encoder_frames):
            segments, _ = self.whisper.transcribe(audio, language='es', beam_size=3,
                vad_filter=False, condition_on_previous_text=False, without_timestamps=True,
                max_new_tokens=1)
            list(segments)  # faster-whisper starts inference when this is consumed.
            segments, _ = self.whisper.transcribe(audio, language='es', beam_size=3,
                vad_filter=True, condition_on_previous_text=False)
            list(segments)

    @contextmanager
    def _encoder_window(self, frames):
        previous=getattr(self._encoder_state,'frames',0)
        self._encoder_state.frames=frames
        try:yield
        finally:self._encoder_state.frames=previous

    def _load_voice(self):
        if not self.installed():
            raise RuntimeError("Download the configured local Spanish voice before starting voice service")
        if self.voice is None:
            from piper import PiperVoice
            self.voice=PiperVoice.load(str(self.voice_path))

    def _load_transcriber(self):
        if self.whisper is None:
            from faster_whisper import WhisperModel
            self.whisper = WhisperModel(self.whisper_model, device="cpu", compute_type="int8",
                                        cpu_threads=4, download_root=str(self.model_dir) if self.model_dir else None)
            if self.encoder_frames:
                encode=self.whisper.encode
                state=self._encoder_state
                def bounded_encode(features):
                    frames=getattr(state,'frames',0)
                    return encode(features[..., :frames] if frames else features)
                # faster-whisper 1.2 pads every encoder input to 30 seconds;
                # installed CTranslate2 accepts the shorter positional window.
                # This instance-local hook retains the normal decoder/VAD.
                self.whisper.encode=bounded_encode

    def transcribe(self, pcm: bytes) -> str:
        if self.whisper is None:
            self._load_transcriber()
        audio = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768
        # Microphone uploads are capped at 8 seconds. Legacy callers supplying
        # even one additional sample retain the full encoder; never drop speech
        # to obtain a faster result. Keep the window active through lazy decode.
        frames=self.encoder_frames if len(audio)<=RATE*8 else 0
        with self._encoder_window(frames):
            segments, _ = self.whisper.transcribe(audio, language="es", beam_size=3,
                initial_prompt='Conversación en español con Mochi. Cuánto, cómo, por qué. Operaciones: más, menos, por, entre.',
                vad_filter=True, condition_on_previous_text=False)
            return " ".join(segment.text.strip() for segment in segments).strip()

    def speak(self, text: str) -> bytes:
        if self.voice is None:
            self._load_voice()
        output = io.BytesIO()
        with wave.open(output, "wb") as destination:
            destination.setnchannels(1)
            destination.setsampwidth(2)
            destination.setframerate(24000)
            from piper import SynthesisConfig
            synthesis=SynthesisConfig(speaker_id=self.speaker_id,
                length_scale=self.length_scale*2**(self.pitch_semitones/12),noise_scale=.5,noise_w_scale=.6)
            self.voice.synthesize_wav(text,destination,syn_config=synthesis)
        return wav_to_pcm16(output.getvalue(), self.pitch_semitones)
