"""Install the already published signed OTA, retaining NVS and the previous slot."""
import argparse
import json
from pathlib import Path
import time

import serial
from mochi_device import Device


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', default='COM3')
    parser.add_argument('--version', default='0.13.0-mochi-edu')
    parser.add_argument('--timeout', type=int, default=240)
    args = parser.parse_args()
    report = {'expected': args.version, 'signed_ota': True, 'usb_flash': False, 'validated': False, 'events': []}
    output = Path(__file__).resolve().parents[1] / '.runtime/mochi-education-install.json'
    deadline = time.monotonic() + args.timeout
    requested = False
    try:
        while time.monotonic() < deadline:
            try:
                with Device(args.port) as board:
                    version = board.command('@firmware', '@mochi_firmware', timeout=6)
                    if not report['events'] or report['events'][-1] != version:
                        report['events'].append(version)
                        print(version, flush=True)
                    if 'version=' + args.version + ' ' in version and 'state=2' in version:
                        report['validated'] = True
                        return
                    if not requested:
                        response = board.command('@ota-update', '@mochi_ota_request', timeout=8)
                        report['events'].append(response)
                        print(response, flush=True)
                        requested = 'queued' in response
            except (serial.SerialException, OSError, TimeoutError):
                pass
            time.sleep(1)
        raise TimeoutError('The expected signed OTA did not reach a validated boot before the deadline')
    finally:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
