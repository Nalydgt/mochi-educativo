"""Install only the signed OTA application; retain NVS and previous boot slot."""
import time, json
from pathlib import Path
import serial
from mochi_device import Device

expected = "0.12.6-peluqo-pilot"
events = []
deadline = time.monotonic() + 240
requested = False
while time.monotonic() < deadline:
    try:
        with Device("COM3") as board:
            version = board.command("@firmware", "@mochi_firmware", timeout=12)
            if not events or version != events[-1]:
                print(version, flush=True)
                events.append(version)
            if "version=" + expected + " " in version and "state=2" in version:
                Path(".runtime/peluqo-install.json").write_text(
                    json.dumps(
                        {"version": expected, "validated": True, "events": events},
                        indent=2,
                    )
                )
                raise SystemExit(0)
            if not requested:
                answer = board.command("@ota-update", "@mochi_ota_request", timeout=12)
                print(answer, flush=True)
                events.append(answer)
                requested = True
            try:
                board.reply("@mochi_firmware", timeout=3)
            except TimeoutError:
                pass
    except (serial.SerialException, OSError, TimeoutError):
        pass
    time.sleep(1)
raise TimeoutError(
    "Signed PELUQO OTA did not reach validated boot; prior boot slot and full-flash backup are retained"
)
