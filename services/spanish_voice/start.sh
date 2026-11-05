#!/bin/sh
set -eu
if ! command -v sox >/dev/null 2>&1 || ! test -f /usr/lib/x86_64-linux-gnu/libsndfile.so.1; then
    apt-get update -qq
    apt-get install -y --no-install-recommends git ca-certificates libsndfile1 libgomp1 sox
fi
if ! test -x /runtime/venv/bin/python; then python -m venv /runtime/venv; fi
if ! test -f /runtime/installed-v1; then
    /runtime/venv/bin/pip install --no-cache-dir 'setuptools==80.10.2' wheel
    /runtime/venv/bin/pip install --no-cache-dir 'torch==2.9.1' 'torchaudio==2.9.1' --index-url https://download.pytorch.org/whl/cpu
    /runtime/venv/bin/pip install --no-cache-dir -r /app/requirements.txt
    /runtime/venv/bin/pip install --no-deps --no-cache-dir 'git+https://github.com/resemble-ai/chatterbox.git@5de7a54aa4e5e2baadb0182dde554908b48b85c2'
    touch /runtime/installed-v1
fi
exec /runtime/venv/bin/uvicorn server:app --host 0.0.0.0 --port 8767 --workers 1 --no-access-log
