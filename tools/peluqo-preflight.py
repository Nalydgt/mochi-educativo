"""Read-only board preflight; no reset and no personal settings change."""
import json
from pathlib import Path
from mochi_device import Device

results = []
with Device("COM3") as board:
    for command, prefix in [
        ("@firmware", "@mochi_firmware"),
        ("@status", "@mochi_status"),
        ("@resources", "@mochi_resources"),
        ("@vpn-test", "@mochi_vpn_test"),
        ("@voice-policy-test", "@mochi_voice_policy_test"),
    ]:
        result = board.command(command, prefix, timeout=15)
        results.append(result)
        print(result, flush=True)
Path(".runtime/peluqo-preflight.json").write_text(
    json.dumps({"checks": results}, indent=2)
)
