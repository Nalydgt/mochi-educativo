#!/bin/sh
set -eu
/app/llama-server --list-devices > /model-cache/devices.txt 2>&1
exec /app/llama-server "$@" >> /model-cache/startup.log 2>&1
