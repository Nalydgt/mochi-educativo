from pathlib import Path

import numpy as np

from speech import LocalSpeech, RATE


def test_startup_runs_decoder_and_vad_lazily_before_first_recording():
    completed = []

    class Transcriber:
        def transcribe(self, audio, **options):
            assert audio.dtype == np.float32 and len(audio) == RATE
            assert not np.any(audio)
            def segments():
                completed.append(options)
                return
                yield
            return segments(), None

    speech = LocalSpeech(Path('unused'))
    speech.whisper = Transcriber()
    speech.warmup_transcriber()
    assert [options['vad_filter'] for options in completed] == [False, True]
    assert completed[0]['max_new_tokens'] == 1
    assert all(options['language'] == 'es' for options in completed)


def test_asr_window_setting_reaches_the_serving_transcriber(tmp_path, monkeypatch):
    from app import Settings
    monkeypatch.setenv('WHISPER_ENCODER_FRAMES', '1600')
    monkeypatch.setenv('WHISPER_MODEL', str(tmp_path/'verified-small'))
    settings = Settings.from_env()
    transcriber = settings.local_speech()
    assert transcriber.encoder_frames == 1600
    assert transcriber.whisper_model == str(tmp_path/'verified-small')
