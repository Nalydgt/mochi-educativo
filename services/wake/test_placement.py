import numpy as np
from placement import positive_context,trim_quiet


def test_positive_window_never_loses_either_end_of_keyword():
    rng=np.random.default_rng(3)
    # A marked first and last segment reveal any temporal clipping.
    keyword=np.full(14000,3000,dtype=np.int16)
    keyword[:800]=8000;keyword[-800:]=-8000
    seen=0
    for _ in range(200):
        sequence=positive_context(keyword,np.zeros(32000,dtype=np.int16),rng,20480)
        if sequence is None:continue
        window=sequence[-20480:]
        peak=max(float(window.max()),-float(window.min()))
        assert np.count_nonzero(window>peak*.7)>100
        assert np.count_nonzero(window<-peak*.7)>100
        seen+=1
    assert seen>150


def test_long_keyword_is_rejected_instead_of_cropped():
    assert positive_context(np.ones(40000,dtype=np.int16)*1000,np.zeros(32000),np.random.default_rng(0),20480) is None


def test_silence_trim_keeps_boundary_margin():
    audio=np.concatenate([np.zeros(3200),np.ones(3200)*3000,np.zeros(3200)]).astype(np.int16)
    trimmed=trim_quiet(audio)
    assert len(trimmed)==4480
    assert np.array_equal(trimmed[640:3840],audio[3200:6400])
