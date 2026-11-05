"""Prepare/apply the exact installed Hermes API disconnect patch; never restart services."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile


SUPPORTED_SOURCE_SHA256 = '4930c2b53cabd110af1dc744974b88fba90245fb1b5caf8f832da3672a0f1159'
INSERT_BEFORE = 'async def _iter_stream_items(stream_q, agent_task, response):\n'
CHAT_CONTEXT = '''        async def _compute_completion():
            return await self._run_agent(**run_kwargs)
'''
RESPONSES_CONTEXT = '''        async def _compute_response():
            return await self._run_agent(**run_kwargs)
'''


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def guard_source() -> str:
    path = Path(__file__).with_name('disconnect_guard.py')
    source = path.read_text(encoding='utf-8')
    module = ast.parse(source)
    function = next(node for node in module.body if isinstance(node, ast.AsyncFunctionDef))
    lines = source.splitlines(keepends=True)
    return ''.join(lines[function.lineno - 1:function.end_lineno]).rstrip() + '\n\n\n'


def patched_source(raw: bytes) -> bytes:
    if sha256(raw) != SUPPORTED_SOURCE_SHA256:
        raise ValueError('Installed Hermes API source hash differs from the reviewed version')
    source = raw.decode('utf-8')
    for context in (INSERT_BEFORE, CHAT_CONTEXT, RESPONSES_CONTEXT):
        if source.count(context) != 1:
            raise ValueError('Reviewed Hermes API context is not unique')
    source = source.replace(INSERT_BEFORE, guard_source() + INSERT_BEFORE, 1)
    for context in (CHAT_CONTEXT, RESPONSES_CONTEXT):
        replacement = context.replace('return await self._run_agent(**run_kwargs)',
            'return await _mochi_run_bound_nonstream(self, request, run_kwargs)')
        source = source.replace(context, replacement, 1)
    compile(source, 'api_server_openai_routes.py', 'exec')
    return source.encode('utf-8')


def prepare(source: Path, output: Path) -> dict:
    raw = source.read_bytes()
    candidate = patched_source(raw)
    if output.resolve() == source.resolve():
        raise ValueError('Preparation must not overwrite installed code')
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and output.read_bytes() != candidate:
        raise ValueError('Preserve the existing different candidate')
    output.write_bytes(candidate)
    return {'source_sha256': sha256(raw), 'candidate_sha256': sha256(candidate),
            'source_bytes': len(raw), 'candidate_bytes': len(candidate), 'installed': False}


def apply(source: Path, backup: Path) -> dict:
    raw = source.read_bytes()
    candidate = patched_source(raw)
    metadata = source.stat()
    backup.mkdir(parents=True, exist_ok=True)
    original = backup / source.name
    if original.exists() and original.read_bytes() != raw:
        raise ValueError('Existing backup differs; choose a fresh backup directory')
    shutil.copy2(source, original)
    if original.read_bytes() != raw:
        raise ValueError('Backup verification failed')
    descriptor, temporary = tempfile.mkstemp(prefix=source.name + '.', dir=source.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(candidate)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, metadata.st_mode)
        if hasattr(os, 'chown'):
            os.chown(temporary, metadata.st_uid, metadata.st_gid)
        # Recheck immediately before atomic replacement; never overwrite drift.
        if source.read_bytes() != raw:
            raise ValueError('Installed code changed during preparation')
        os.replace(temporary, source)
    finally:
        Path(temporary).unlink(missing_ok=True)
    if source.read_bytes() != candidate:
        raise ValueError('Installed patch verification failed')
    return {'source_sha256': sha256(raw), 'candidate_sha256': sha256(candidate),
            'backup': str(original), 'installed': True, 'service_restarted': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'apply'))
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--backup', type=Path)
    args = parser.parse_args()
    if args.action == 'prepare':
        if args.output is None:
            parser.error('prepare requires --output')
        report = prepare(args.source, args.output)
    else:
        if args.backup is None:
            parser.error('apply requires --backup')
        report = apply(args.source, args.backup)
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
