"""Keep the complete activation word inside every positive training window."""
import numpy as np


def trim_quiet(audio):
    audio=np.asarray(audio,dtype=np.int16)
    if not len(audio):return audio
    width=160
    padded=np.pad(audio.astype(np.float32),(0,(-len(audio))%width))
    rms=np.sqrt(np.mean(padded.reshape(-1,width)**2,axis=1))
    active=np.flatnonzero(rms>max(20,float(rms.max())*.015))
    if not len(active):return audio
    start=max(0,int(active[0])*width-640)
    end=min(len(audio),(int(active[-1])+1)*width+640)
    return audio[start:end]


def positive_context(keyword,context,rng,window_samples):
    """Return None for an oversized word rather than teaching a clipped syllable."""
    keyword=trim_quiet(keyword).astype(np.float32)
    ratio=rng.uniform(.85,1.15)
    length=max(1,int(len(keyword)/ratio))
    if length>window_samples-1280:return None
    word=np.interp(np.arange(length)*ratio,np.arange(len(keyword)),keyword)
    word*=rng.uniform(.3,1.)
    rms=max(1,float(np.sqrt(np.mean(word**2))))
    word+=rng.normal(0,rms/10**(rng.uniform(12,32)/20),length)
    # End jitter is constrained by the actual word length. Cropping the last
    # feature window can therefore never remove the beginning of the keyword.
    tail_size=int(rng.integers(0,min(2400,window_samples-length-640)+1))
    tail=rng.normal(0,rng.uniform(0,70),tail_size)
    sequence=np.concatenate([context,word,tail])
    return np.clip(sequence,-32768,32767).astype(np.int16)
