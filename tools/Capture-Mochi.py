"""Capture actual LVGL pixels over local USB; no extra image library needed."""
import argparse
from pathlib import Path
import re
import struct
import time
import zlib

import serial


def png_chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--port", default="COM3")
    parser.add_argument("--state", default="happy")
    parser.add_argument("--delay", type=float, default=.8)
    parser.add_argument("--settings", action="store_true")
    parser.add_argument("--dashboard",type=int,choices=(0,2,3,5,8,9))
    parser.add_argument("--current",action='store_true',help='Inspect the current UI without changing its state')
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z]+", args.state):
        parser.error("Invalid state")
    port = serial.Serial(port=None, baudrate=115200, timeout=1)
    port.dtr = port.rts = False
    port.port = args.port
    with port:
        if hasattr(port, "set_buffer_size"):
            port.set_buffer_size(rx_size=1024 * 1024)
        port.reset_input_buffer()
        command=("@dashboard "+str(args.dashboard)+"\n").encode() if args.dashboard is not None else b"@settings\n" if args.settings else ("@emote " + args.state + "\n").encode()
        if not args.current: port.write(command)
        time.sleep(max(0, args.delay))
        port.write(b"@frame\n")
        width = height = 0
        rows = {}
        pending = bytearray()
        finished = False
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline and not finished:
            pending.extend(port.read(8192))
            while b"\n" in pending:
                line, _, pending = pending.partition(b"\n")
                line = line.strip()
                match = re.search(rb"@mochi_frame (\d+) (\d+)$", line)
                if match:
                    width, height = map(int, match.groups())
                    print(f"Frame {width}x{height}", flush=True)
                if b"@mochi_frame error" in line:
                    raise SystemExit("Device could not allocate or render a snapshot.")
                match = re.search(rb"@mochi_row (\d+) ([0-9a-f]+)$", line)
                if match and len(match[2]) == width * 4:
                    rows[int(match[1])] = bytes.fromhex(match[2].decode())
                if b"@mochi_frame_end" in line:
                    finished = True
                    break
    if not (0 < width <= 466 and 0 < height <= 466) or set(rows) != set(range(height)):
        raise SystemExit(f"Incomplete frame: {width}x{height}, {len(rows)} rows received; close other serial monitors and retry.")
    raw = bytearray()
    for y in range(height):
        if len(rows[y]) != width * 2:
            raise SystemExit("Invalid row length")
        raw.append(0)  # PNG filter: none
        for (pixel,) in struct.iter_unpack("<H", rows[y]):
            red, green, blue = (pixel >> 11) & 31, (pixel >> 5) & 63, pixel & 31
            raw.extend(((red << 3) | (red >> 2), (green << 2) | (green >> 4), (blue << 3) | (blue >> 2)))
    png = b"\x89PNG\r\n\x1a\n"
    png += png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += png_chunk(b"IDAT", zlib.compress(raw))
    png += png_chunk(b"IEND", b"")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(png)
    print(str(args.output.resolve()))


if __name__ == "__main__":
    main()
