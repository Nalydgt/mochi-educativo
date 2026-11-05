"""Verify task-scoped ASR/tutor/TTS with a synthetic fixture, without recording a child."""
import argparse
import json
from pathlib import Path
import time
from uuid import uuid4
import wave

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wav', type=Path, default=ROOT / '.runtime/education-synthetic-teach.wav')
    parser.add_argument('--connector', default='http://127.0.0.1:54321')
    args = parser.parse_args()
    device_file = ROOT / 'web/.runtime/mochi-education-device.json'
    device = json.loads(device_file.read_text(encoding='utf-8'))
    with wave.open(str(args.wav), 'rb') as fixture:
        if (fixture.getframerate(), fixture.getnchannels(), fixture.getsampwidth()) != (16000, 1, 2):
            raise ValueError('The synthetic fixture must be PCM16 mono at 16 kHz')
        pcm = fixture.readframes(fixture.getnframes())
    started = time.monotonic()
    response = httpx.post(args.connector + '/v1/education/turn',
        headers={'Authorization': 'Bearer ' + device['token'], 'Content-Type': 'application/octet-stream',
                 'X-Mochi-Turn-ID': str(uuid4())}, content=pcm, timeout=210)
    kind = response.headers.get('x-mochi-education-reply', 'unverified')
    valid_audio = response.status_code == 200 and len(response.content) > 3200 and len(response.content) % 2 == 0 and response.headers.get('x-mochi-sample-rate') == '16000'
    report = {'passed': valid_audio and kind == 'tutor', 'data': 'fictional_demonstration',
              'input': 'locally_synthesized_spanish_fixture', 'microphone_recorded': False,
              'physical_speaker_tested': False, 'model_runs_on_esp32': False,
              'http': response.status_code, 'reply_kind': kind, 'pcm_bytes': len(response.content) if valid_audio else 0,
              'elapsed_seconds': round(time.monotonic() - started, 3), 'audio_or_transcript_published': False}
    if valid_audio:
        (ROOT / '.runtime/education-tutor-reply.pcm').write_bytes(response.content)
    output = ROOT / 'docs/mediciones/20261105-mochi-voz-educativa.json'
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(report), flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
