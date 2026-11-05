"""USB-stat retries must never replay audio or accept a stale playback record."""
import importlib.util
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location('mochi_navigation_validation', Path(__file__).with_name('Validate-MochiNavigation.py'))
validation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validation)


class Device:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.commands = []

    def command(self, command, prefix, timeout):
        self.commands.append(command)
        assert command == '@audio' and prefix == '@mochi_playback' and timeout == 3
        result = next(self.replies)
        if isinstance(result, Exception):
            raise result
        return result


def test_valid_playback_requires_one_read_only_query():
    device = Device(['@mochi_playback pcm_ms=1000 wall_ms=1150 lead_ms=128'])
    assert validation.playback_diagnostic(device, 32000) == {
        'pcm_ms': 1000, 'wall_ms': 1150, 'diagnostic_retries': 0}
    assert device.commands == ['@audio']


def test_lost_reply_retries_diagnostic_without_replaying_the_cue():
    device = Device([TimeoutError(), '@mochi_playback pcm_ms=1000 wall_ms=1150 lead_ms=128'])
    assert validation.playback_diagnostic(device, 32000)['diagnostic_retries'] == 1
    assert device.commands == ['@audio', '@audio']


def test_second_lost_reply_fails_instead_of_inventing_measurements():
    device = Device([TimeoutError(), TimeoutError()])
    with pytest.raises(TimeoutError):
        validation.playback_diagnostic(device, 32000)
    assert device.commands == ['@audio', '@audio']


def test_old_cue_duration_is_rejected_even_when_wall_time_is_plausible():
    device = Device(['@mochi_playback pcm_ms=500 wall_ms=650 lead_ms=128'])
    with pytest.raises(RuntimeError, match='does not match'):
        validation.playback_diagnostic(device, 32000)
