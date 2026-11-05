#!/bin/sh
set -eu
if ! test -x /data/gateway-runtime/venv/bin/python; then
    python -m venv /data/gateway-runtime/venv
fi
if ! cmp -s /app/requirements.txt /data/gateway-runtime/requirements.installed.txt; then
    /data/gateway-runtime/venv/bin/python -m pip install --disable-pip-version-check --no-cache-dir --require-hashes -r /app/requirements.txt
    cp /app/requirements.txt /data/gateway-runtime/requirements.installed.txt
fi
/data/gateway-runtime/venv/bin/python /app/bootstrap.py
exec /data/gateway-runtime/venv/bin/uvicorn app:app_factory --factory --host 0.0.0.0 --port 8765 --no-access-log
