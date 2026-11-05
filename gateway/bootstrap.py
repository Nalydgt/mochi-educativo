"""Prepare local speech models inside the container; never record or play audio."""
import urllib.request
from pathlib import Path

from faster_whisper.utils import download_model

from app import Settings

settings = Settings.from_env()
data, voice = settings.data_dir, settings.voice_path
if settings.voice_provider in {'native', 'elevenlabs'}:
    downloads = []
elif settings.voice_engine == "piper":
    models = {"es_ES-sharvard-medium.onnx": "es/es_ES/sharvard/medium/",
              "es_ES-carlfm-x_low.onnx": "es/es_ES/carlfm/x_low/",
              "es_ES-davefx-medium.onnx": "es/es_ES/davefx/medium/"}
    if voice.name not in models:
        raise RuntimeError("Configured voice is not in the local download catalog")
    base = "https://huggingface.co/rhasspy/piper-voices/resolve/main/" + models[voice.name]
    downloads = [(base + name, voice.parent / (voice.stem + "-MODEL_CARD" if name == "MODEL_CARD" else name))
                 for name in [voice.name, voice.name + ".json", "MODEL_CARD"]]
else:
    raise RuntimeError("Unsupported local speech engine")
for url, target in downloads:
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        print("Preparing Spanish voice:", target.name, flush=True)
        temporary = target.with_suffix(target.suffix + ".download")
        with urllib.request.urlopen(url, timeout=120) as source, temporary.open("wb") as destination:
            while chunk := source.read(1024 * 1024):
                destination.write(chunk)
        temporary.replace(target)
print("Preparing speech recognition model", flush=True)
if not Path(settings.whisper_model).is_dir():
    download_model(settings.whisper_model, cache_dir=str(data / "models"))
print("Local speech files ready; the serving process will load the models", flush=True)
