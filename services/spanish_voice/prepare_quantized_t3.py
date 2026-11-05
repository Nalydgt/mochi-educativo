"""Prepare an isolated T3 weight experiment; this never runs speech inference.

Uses the verified V3 source weights and the upstream tensor deny-list. All
reference encoders, embeddings and conditioning remain at full precision.
Neither this tool nor its outputs select a production voice/profile.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time


V3 = 't3_mtl23ls_v3.safetensors'
V3_SHA256 = '5abca8321ede76f8e61f1cc0d19aea6c946b28871017ce8726f8a69203f05953'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets', type=Path, required=True)
    parser.add_argument('--upstream', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--quant', choices=('q8_0', 'q5_0', 'q4_0'), nargs='+', default=['q5_0', 'q4_0'])
    args = parser.parse_args()
    if len(set(args.quant)) != len(args.quant):
        raise ValueError('Quantization choices must be distinct')
    if args.output.exists():
        raise ValueError('Choose a fresh output directory; do not overwrite evidence')
    profile = json.loads((args.assets/'profile.json').read_text(encoding='utf-8'))
    if profile.get('checkpoint') != V3 or profile.get('files', {}).get(V3) != V3_SHA256:
        raise ValueError('This experiment requires the approved original V3 checkpoint')
    for name in (V3, 've.pt', 'conds.pt', 'grapheme_mtl_merged_expanded_v1.json'):
        if digest(args.assets/name) != profile['files'][name]:
            raise ValueError('Voice asset integrity mismatch: ' + name)
    converter = args.upstream/'scripts/convert-t3-mtl-to-gguf.py'
    policy = args.upstream/'scripts/requantize-gguf.py'
    source = converter.read_text(encoding='utf-8')
    legacy = 't3_mtl23ls_v2.safetensors'
    if source.count(legacy) != 2:
        raise ValueError('Review upstream converter before changing its checkpoint')
    args.output.mkdir(parents=True)
    tool_dir = args.output/'converter'
    tool_dir.mkdir()
    (tool_dir/'convert-v3.py').write_text(source.replace(legacy, V3), encoding='utf-8')
    shutil.copyfile(policy, tool_dir/'requantize-gguf.py')
    report = {'weight_conversion_only': True, 'speech_inference_run': False,
              'production_selected': False, 'source_checkpoint_sha256': V3_SHA256,
              'converter_source_sha256': digest(converter), 'quantization_policy_sha256': digest(policy),
              'gguf_version': importlib.metadata.version('gguf'), 'artifacts': []}
    for quant in args.quant:
        target = args.output/('t3-v3-' + quant + '.gguf')
        started = time.monotonic()
        with (args.output/(quant + '.log')).open('wb') as log:
            subprocess.run([sys.executable, str(tool_dir/'convert-v3.py'), '--ckpt-dir', str(args.assets),
                            '--quant', quant, '--out', str(target)], stdout=log, stderr=subprocess.STDOUT,
                           check=True)
        row = {'quantization': quant, 'file': target.name, 'bytes': target.stat().st_size,
               'sha256': digest(target), 'conversion_seconds': round(time.monotonic() - started, 3)}
        report['artifacts'].append(row)
        (args.output/'conversion.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(row), flush=True)


if __name__ == '__main__':
    main()
