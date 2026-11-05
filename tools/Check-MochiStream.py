"""Cancel a cached synthetic speaker probe through settings; no microphone input."""
import argparse
from pathlib import Path
import re
import time

import serial

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--port',default='COM3')
args = parser.parse_args()
port = serial.Serial(port=None,baudrate=115200,timeout=.1)
port.dtr = port.rts = False
port.port = args.port
port.open()
data = bytearray()
try:
    port.reset_input_buffer()
    # USB can retain old log output while the host was disconnected. Drain
    # it before timing a command, rather than mistaking an earlier result.
    drain_until = time.monotonic()+2
    while time.monotonic()<drain_until:
        if not port.read(8192): break
    port.write(b'@speaker-stream-test\n')
    began = time.monotonic()
    finished = False
    next_settings = .7
    while time.monotonic()-began < 20:
        data.extend(port.read(4096))
        if time.monotonic()-began >= next_settings:
            port.write(b'@settings\n')
            next_settings += .25
        if b'@mochi_speaker_stream' in data:
            finished = True
            break
    port.write(b'@status\n@audio\n')
    until = time.monotonic()+5
    next_poll = 0
    while time.monotonic()<until:
        data.extend(port.read(4096))
        if time.monotonic()>=next_poll:
            port.write(b'@close\n@display\n')
            next_poll=time.monotonic()+.4
finally:
    port.write(b'@close\n')
    port.close()
Path('.runtime/stream-cancel-071.log').write_bytes(data)
text = data.decode('utf-8','replace')
response = re.search(r'streamed=1 played=(\d+) first_audio_ms=(\d+)',text)
passed = (finished and response and int(response[1])>0 and
          '@mochi_speaker_stream ready=0' in text and 'result=ESP_ERR_INVALID_STATE' in text and
          re.search(r'@mochi_status .*busy=0',text) and '@mochi_display_ui lock=1' in text)
print('Streaming playback cancellation:', 'PASS' if passed else 'FAIL')
if response: print('Bytes played before cancellation:',response[1])
raise SystemExit(0 if passed else 1)
