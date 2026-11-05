"""Validate benchmark acceptance using synthetic reports only."""
import importlib.util
from pathlib import Path

import pytest


spec=importlib.util.spec_from_file_location('mochi_benchmark',Path(__file__).with_name('Benchmark-Mochi.py'))
benchmark=importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


def measurements(latency):
    return {'questions':[{'index':index,'question':f'Question {index}',
        'status':200,'first_pcm_seconds':latency,'pcm_bytes':32000,
        'pcm_input_sha256':f'input-{index}'} for index in range(20)]}


def test_comparison_matches_question_indices_instead_of_list_order():
    before,after=measurements(10),measurements(5)
    after['questions'].reverse()
    result=benchmark.compare(before,after)
    assert result['accepted'] and result['paired_questions']==20
    assert result['median_reduction_percent']==50
    assert result['first_question_after_seconds']==5


def test_twenty_duplicate_questions_cannot_pass_activation_measurement():
    before,after=measurements(10),measurements(5)
    for run in (before,after):
        for row in run['questions']:row['index']=1
    with pytest.raises(ValueError,match='distinct question indices'):
        benchmark.compare(before,after)


def test_historical_baseline_without_hashes_can_still_be_compared():
    before,after=measurements(10),measurements(5)
    for row in before['questions']:row.pop('pcm_input_sha256')
    assert benchmark.compare(before,after)['accepted']


@pytest.mark.parametrize('change',[
    {'pcm_bytes':0}, {'pcm_bytes':3}, {'pcm_bytes':1440001},
    {'first_pcm_seconds':float('nan')}, {'first_pcm_seconds':float('inf')},
    {'first_pcm_seconds':0}, {'question':'A different recording'},
    {'pcm_input_sha256':'changed input'}, {'status':503},
])
def test_invalid_or_different_measurement_cannot_pass_acceptance(change):
    before,after=measurements(10),measurements(5)
    after['questions'][3].update(change)
    result=benchmark.compare(before,after)
    assert not result['accepted'] and result['paired_questions']==19


def test_missing_cold_question_is_not_reported_as_the_next_warm_question():
    before,after=measurements(10),measurements(5)
    after['questions'].pop(0)
    result=benchmark.compare(before,after)
    assert not result['accepted']
    assert result['first_question_before_seconds'] is None
    assert result['first_question_after_seconds'] is None
