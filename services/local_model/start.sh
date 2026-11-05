#!/bin/sh
set -eu
if ! test -x /runtime/venv/bin/python; then python -m venv /runtime/venv; fi
if ! test -f /runtime/installed-v1; then
    /runtime/venv/bin/pip install --no-cache-dir -r /app/requirements.txt
    touch /runtime/installed-v1
fi
exec /runtime/venv/bin/uvicorn router:app --host 0.0.0.0 --port 8770 --workers 1 --no-access-log
