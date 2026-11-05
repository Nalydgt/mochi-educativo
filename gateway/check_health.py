import json
import os
import urllib.request

request = urllib.request.Request("http://127.0.0.1:8765/health", headers={
    "Authorization": "Bearer " + os.environ["MOCHI_TOKEN"]})
with urllib.request.urlopen(request, timeout=12) as response:
    status = json.load(response)
    if not status.get("profile_ready") or not status.get("voice_installed"):
        raise SystemExit(1)
