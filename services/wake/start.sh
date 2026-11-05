#!/bin/sh
set -eu
if ! test -f /usr/lib/x86_64-linux-gnu/libespeak-ng.so.1; then
    apt-get update -qq
    apt-get install -y --no-install-recommends libespeak-ng1 ca-certificates git
fi
if ! test -x /runtime/venv/bin/python; then python -m venv /runtime/venv; fi
if ! test -f /runtime/installed-v2; then
    /runtime/venv/bin/pip install --no-cache-dir 'tensorflow==2.18.1' 'piper-tts==1.4.0' 'pymicro-features==2.0.2' 'scipy==1.15.3' 'pyyaml==6.0.3' 'pydantic>=2.11,<3' 'cryptography>=45,<48'
    mkdir -p /runtime/source/micro-wake-word
    cp -R /app/micro-wake-word/. /runtime/source/micro-wake-word/
    /runtime/venv/bin/pip install --no-cache-dir /runtime/source/micro-wake-word
    touch /runtime/installed-v2
fi
export PYTHONPATH=/app/gateway
exec /runtime/venv/bin/python /app/wake/worker.py
