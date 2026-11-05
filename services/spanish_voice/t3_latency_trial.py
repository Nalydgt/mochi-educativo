"""Isolated NAS T3 compute/sampling experiment; never selects a serving profile.

The reference matrices are the existing private preparation outputs. No voice
encoder or audio decoder is loaded, so profiling stays below a second full
speaker's memory footprint. Speech tokens are generated only on the NAS.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets', type=Path, required=True)
    parser.add_argument('--conditioning', type=Path, required=True)
    parser.add_argument('--library', action='append', required=True, help='label=/path/to/libmochi-t3.so')
    parser.add_argument('--checkpoint', action='append', required=True, help='label=/path/to/model.gguf')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Choose a fresh report path to preserve earlier evidence')

    import numpy as np
    import torch
    from chatterbox.models.t3.modules.t3_config import T3Config
    from chatterbox.models.tokenizers import MTLTokenizer
    from chatterbox.mtl_tts import punc_norm
    from hybrid_t3 import HybridT3

    torch.set_num_threads(8)
    torch.set_num_interop_threads(1)
    torch.set_flush_denormal(True)
    profile = json.loads((args.assets/'profile.json').read_text())
    if profile.get('decoder_cfm_steps', 4) != 4:
        raise ValueError('Keep the approved four-step recipe while profiling T3')
    conditioning = SimpleNamespace(
        speaker_emb=torch.from_numpy(np.load(args.conditioning/'speaker_emb.npy')).reshape(1, -1),
        cond_prompt_speech_tokens=torch.from_numpy(np.load(args.conditioning/'cond_prompt_speech_tokens.npy')).reshape(1, -1),
        emotion_adv=torch.tensor([[[profile['exaggeration']]]], dtype=torch.float32))
    tokenizer = MTLTokenizer(str(args.assets/'grapheme_mtl_merged_expanded_v1.json'))
    hp = T3Config.multilingual()
    libraries = dict(value.split('=', 1) for value in args.library)
    checkpoints = dict(value.split('=', 1) for value in args.checkpoint)
    report = {'nas_inference_only': True, 'audio_decoder_run': False,
              'production_selected': False, 'results': []}
    references = {}
    texts = ('Puedo ayudarte con eso.',
             'La nieve nace en las nubes cuando el vapor de agua se convierte en hielo.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for library_name, library in libraries.items():
        # Load verified dependency libraries alongside the original build.
        dependency_root = Path(library).parent
        for name in ('libggml-base.so', 'libggml-cpu.so', 'libggml.so'):
            path = dependency_root/name
            if path.is_file():
                ctypes.CDLL(str(path), mode=ctypes.RTLD_GLOBAL)
        for checkpoint_name, checkpoint in checkpoints.items():
            adapter = HybridT3(library, checkpoint, conditioning, hp, seed=profile['seed'], threads=8)
            native = adapter.lib.mochi_t3_logits
            totals = {}
            def measured(*values):
                started = perf_counter()
                try:
                    return native(*values)
                finally:
                    key = 'prefill' if values[4] == 0 else 'steps'
                    totals[key] = totals.get(key, 0.0) + perf_counter() - started
            adapter.lib.mochi_t3_logits = measured
            try:
                for text_index, text in enumerate(texts):
                    ids = tokenizer.text_to_tokens(punc_norm(text), language_id='es')
                    ids = torch.cat((ids, ids), dim=0)
                    ids = torch.nn.functional.pad(ids, (1, 0), value=hp.start_text_token)
                    ids = torch.nn.functional.pad(ids, (0, 1), value=hp.stop_text_token)
                    # Repeat the original setting around the one-thread
                    # sampler test, so a cold first call cannot masquerade
                    # as a sampling improvement. The longer phrase checks
                    # throughput once both paths have already been exercised.
                    for run_index, sampler_threads in enumerate((8, 1, 8) if text_index == 0 else (8,)):
                        torch.set_num_threads(sampler_threads)
                        torch.manual_seed(profile['seed'])
                        totals.clear()
                        started = perf_counter()
                        with torch.inference_mode():
                            tokens = adapter.inference(t3_cond=conditioning, text_tokens=ids,
                                temperature=profile['temperature'], cfg_weight=profile['cfg_weight'])
                        elapsed = perf_counter() - started
                        data = tokens.numpy().astype('<i8').tobytes()
                        digest = hashlib.sha256(data).hexdigest()
                        reference = references.setdefault(text_index, digest)
                        row = {'library': library_name, 'checkpoint': checkpoint_name,
                               'text_index': text_index, 'run_index': run_index,
                               'sampler_threads': sampler_threads,
                               'seconds': round(elapsed, 6),
                               'native_prefill_seconds': round(totals.get('prefill', 0), 6),
                               'native_steps_seconds': round(totals.get('steps', 0), 6),
                               'sampling_and_bridge_seconds': round(elapsed - sum(totals.values()), 6),
                               'speech_tokens_including_eos': tokens.numel(), 'tokens_sha256': digest,
                               'speech_tokens_per_second': round((tokens.numel()-1)/elapsed, 4),
                               'identical_tokens_to_first_reference': digest == reference}
                        report['results'].append(row)
                        args.output.write_text(json.dumps(report, indent=2) + '\n')
                        print(json.dumps(row), flush=True)
            finally:
                adapter.close()
    report['finished'] = True
    args.output.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
