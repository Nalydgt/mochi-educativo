"""Bounded USB diagnostics for the personal Mochi board."""
import serial,re,time


def voice_timings(fields):
    """Keep queued PCM, completed I2S DMA and acoustic sound distinct."""
    result = {'physical_first_sound_measured': False}
    for field, name in (('first_audio_ms', 'first_queued_seconds'),
                        ('first_pcm_ms', 'first_pcm_seconds'),
                        ('first_i2s_ms', 'first_i2s_seconds')):
        if fields.get(field, -1) >= 0:
            result[name] = fields[field] / 1000
    result['first_i2s_measured'] = 'first_i2s_seconds' in result
    if result['first_i2s_measured']:
        result['first_i2s_event'] = 'first_nonzero_dma_completion'
        if 'i2s_tick_ms' in fields:
            result['first_i2s_tick_ms'] = fields['i2s_tick_ms']
    return result


class Device:
    def __init__(self, port):
        self.port = serial.Serial(port=None, baudrate=115200, timeout=.01, write_timeout=10)
        self.port.dtr = self.port.rts = False
        self.port.port = port
        self.pending = bytearray()
        self.events = []

    def __enter__(self):
        self.port.open()
        self.port.reset_input_buffer()
        self.port.write(b"\n")
        time.sleep(.5)
        return self

    def __exit__(self, *args):
        self.port.close()

    def command(self, text, prefix, timeout=15, accept=None):
        if len(text.encode()) > 1198 or "\n" in text or "\r" in text:
            raise ValueError("Command exceeds the device's line contract")
        self.port.write((text + "\n").encode())
        return self.reply(prefix, timeout, accept)

    def reply(self, prefix, timeout=15, accept=None):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            # A short, buffered read avoids per-byte Win32 calls and long waits
            # for a 4 KiB buffer on thousands of small USB acknowledgements.
            self.pending.extend(self.port.read(4096))
            while b"\n" in self.pending:
                line, _, tail = self.pending.partition(b"\n")
                self.pending[:] = tail
                decoded = line.decode("utf-8", "replace").strip()
                for event_prefix in ("@mochi_av_test ", "@mochi_speaker_stream ", "@mochi_mic_speaker ", "Voice response: "):
                    event_start=decoded.find(event_prefix)
                    if event_start>=0:
                        self.events.append(decoded[event_start:])
                if re.search(r"assert failed|Guru Meditation|Backtrace:|Stack canary", decoded):
                    raise RuntimeError("Device fault: " + decoded[:500])
                # Opening native USB can leave the tail of a log line before
                # the first reply; match the protocol marker within that line.
                marker = decoded.find(prefix)
                if marker >= 0:
                    result = decoded[marker:]
                    if accept is None or accept(result):
                        return result
            if len(self.pending) > 16384:
                raise RuntimeError("Unterminated device output")
        raise TimeoutError(f"No {prefix} response")
