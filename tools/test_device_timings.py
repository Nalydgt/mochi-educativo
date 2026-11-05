"""Latency reports must not call queued network audio actual DAC output."""
from mochi_device import voice_timings


def test_legacy_queue_timestamp_is_not_reported_as_i2s_or_acoustic_sound():
    report = voice_timings({'first_audio_ms': 1000})
    assert report['first_queued_seconds'] == 1
    assert report['first_i2s_measured'] is False
    assert 'first_i2s_seconds' not in report
    assert report['physical_first_sound_measured'] is False


def test_completed_dma_is_distinct_from_receiving_and_queueing_pcm():
    report = voice_timings({'first_pcm_ms': 980, 'first_audio_ms': 1000,
                            'first_i2s_ms': 1143, 'i2s_tick_ms': 1})
    assert report['first_pcm_seconds'] == .98
    assert report['first_queued_seconds'] == 1
    assert report['first_i2s_seconds'] == 1.143
    assert report['first_i2s_measured'] is True
    assert report['first_i2s_event'] == 'first_nonzero_dma_completion'
    assert report['first_i2s_tick_ms'] == 1
    assert report['physical_first_sound_measured'] is False


def test_unobserved_output_is_not_reported_as_negative_latency():
    report = voice_timings({'first_audio_ms': -1, 'first_pcm_ms': -1, 'first_i2s_ms': -1})
    assert report == {'physical_first_sound_measured': False, 'first_i2s_measured': False}
