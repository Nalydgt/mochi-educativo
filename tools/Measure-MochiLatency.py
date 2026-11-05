"""Measure frozen synthetic recordings through ASR, model and the selected voice.

Fresh audio generation is the default: a repeated cached phrase cannot prove
latency for a new answer. This measures first HTTP PCM, not physical sound.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import statistics
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import uuid
import wave

ROOT = Path(__file__).resolve().parents[1]


def measure(base, token, inputs, fixture, output, target=2.0, use_cache=False):
    device = 'mochi-diagnostics-latency-' + uuid.uuid4().hex[:12]
    report = {'synthetic': True, 'microphone_used': False,
              'physical_first_sound_measured': False,
              'audio_cache': 'use' if use_cache else 'bypass',
              'target_first_pcm_seconds': target, 'questions': []}
    output.parent.mkdir(parents=True, exist_ok=True)
    for item in inputs:
        path = fixture / item['file']
        if hashlib.sha256(path.read_bytes()).hexdigest() != item['wav_sha256']:
            raise ValueError('Frozen WAV integrity check failed')
        with wave.open(str(path), 'rb') as source:
            if (source.getframerate(), source.getsampwidth(), source.getnchannels()) != (16000, 2, 1):
                raise ValueError('Expected PCM16 mono at 16 kHz')
            pcm = source.readframes(source.getnframes())
        if hashlib.sha256(pcm).hexdigest() != item['pcm_sha256']:
            raise ValueError('Frozen PCM integrity check failed')
        headers = {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/octet-stream',
                   'X-Device-ID': device, 'X-Mochi-Stream': 'pcm16',
                   'X-Mochi-Turn-ID': 'latency-' + uuid.uuid4().hex,
                   'X-Mochi-Audio-Cache': report['audio_cache']}
        row = {'index': item['index'], 'question': item['question'],
               'pcm_input_sha256': item['pcm_sha256'], 'exchange_id': headers['X-Mochi-Turn-ID']}
        start = time.monotonic()
        try:
            with urlopen(Request(base.rstrip('/') + '/v1/turn', data=pcm, headers=headers), timeout=180) as response:
                first = response.read(2)
                row['first_pcm_seconds'] = round(time.monotonic() - start, 3)
                audio = first + response.read(1440001)
                row.update(status=response.status, pcm_bytes=len(audio),
                           brain_route=response.headers.get('X-Mochi-Route'),
                           exchange_id=response.headers.get('X-Mochi-Turn-ID'),
                           stages_ms={k: float(v) for k, v in re.findall(
                               r'([a-z_]+);dur=([0-9.]+)', response.headers.get('Server-Timing', ''))})
                row['valid'] = (len(first) == 2 and 2 <= len(audio) <= 1440000 and len(audio) % 2 == 0
                                and response.headers.get('X-Mochi-Sample-Rate') == '16000'
                                and response.headers.get('X-Mochi-Stream') == 'pcm16'
                                and response.headers.get('X-Mochi-Audio-Cache') == report['audio_cache'])
        except HTTPError as exc:
            row.update(valid=False, error=type(exc).__name__, status=exc.code)
        except Exception as exc:
            row.update(valid=False, error=type(exc).__name__)
        row['total_seconds'] = round(time.monotonic() - start, 3)
        report['questions'].append(row)
        successful = [r['first_pcm_seconds'] for r in report['questions'] if r['valid']]
        report['all_responses_valid'] = all(r['valid'] for r in report['questions'])
        report['near_immediate_verified'] = (len(report['questions']) == len(inputs)
            and report['all_responses_valid'] and max(successful, default=float('inf')) <= target)
        report['median_first_pcm_seconds'] = statistics.median(successful) if successful else None
        report['max_first_pcm_seconds'] = max(successful) if successful else None
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(row, ensure_ascii=False), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--settings', type=Path, default=ROOT/'.runtime/nas.json')
    parser.add_argument('--url')
    parser.add_argument('--indices', default=','.join(map(str, range(20))))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--target', type=float, default=2.0)
    parser.add_argument('--use-cache', action='store_true')
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('Choose a new report path to preserve previous evidence')
    if args.target <= 0:
        raise SystemExit('Target must be positive')
    settings = json.loads(args.settings.read_text(encoding='utf-8'))
    token = (ROOT/settings['device_key_file']).read_text().strip()
    fixture = ROOT/'tests/fixtures/synthetic'
    manifest = json.loads((fixture/'manifest.json').read_text(encoding='utf-8'))['inputs']
    indices = list(map(int, args.indices.split(',')))
    if not indices or len(indices) != len(set(indices)) or any(i not in range(len(manifest)) for i in indices):
        raise SystemExit('Expected distinct corpus indices from 0 to 19')
    report = measure(args.url or 'http://' + settings['host'] + ':8765', token,
                     [manifest[i] for i in indices], fixture, args.output, args.target, args.use_cache)
    print(json.dumps({k: v for k, v in report.items() if k != 'questions'}), flush=True)


if __name__ == '__main__':
    main()
