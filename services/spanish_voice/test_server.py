"""Exercise HTTP policy and native-resource lifetime without loading voice weights."""
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType,SimpleNamespace
import wave

from fastapi import HTTPException
import pytest


@pytest.fixture
def server(monkeypatch):
    monkeypatch.setenv('MOCHI_NATIVE_TOKEN','local-voice-test-'*3)
    monkeypatch.setenv('MOCHI_NATIVE_DEVICE','cpu')
    spec=importlib.util.spec_from_file_location('mochi_voice_server',Path(__file__).with_name('server.py'))
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fake_startup(server,monkeypatch,tmp_path,channels=1,steps=4):
    monkeypatch.setattr(server,'ROOT',tmp_path)
    profile={'schema':1,'language':'es','files':{},'seed':4139,'checkpoint':'verified',
        'exaggeration':.25,'backend':'ggml-t3-torch-decoder','decoder_threads':4,
        'decoder_cfm_steps':steps}
    (tmp_path/'profile.json').write_text(json.dumps(profile),encoding='utf-8')
    with wave.open(str(tmp_path/'approved.wav'),'wb') as output:
        output.setnchannels(channels);output.setsampwidth(2);output.setframerate(16000)
        output.writeframes(b'\0\0'*channels*16)
    model=SimpleNamespace(prepare_conditionals=lambda *args,**kwargs:None,
        t3=SimpleNamespace(inference=lambda:None),s3gen=SimpleNamespace(inference=lambda:None))
    torch=ModuleType('torch')
    for name in ('set_num_threads','set_num_interop_threads','set_flush_denormal','manual_seed'):
        setattr(torch,name,lambda *args:None)
    chatterbox=ModuleType('chatterbox.mtl_tts')
    chatterbox.ChatterboxMultilingualTTS=SimpleNamespace(from_local=lambda *args,**kwargs:model)
    assets=ModuleType('hybrid_assets')
    class Adapter:
        closed=False
        def close(self):self.closed=True
    adapter=Adapter()
    assets.install=lambda *args:adapter
    monkeypatch.setitem(sys.modules,'torch',torch)
    monkeypatch.setitem(sys.modules,'chatterbox',ModuleType('chatterbox'))
    monkeypatch.setitem(sys.modules,'chatterbox.mtl_tts',chatterbox)
    monkeypatch.setitem(sys.modules,'hybrid_assets',assets)
    monkeypatch.setattr(server,'generate_pcm',lambda text:b'\0\0')
    return adapter


@pytest.mark.parametrize('channels,steps,message',[
    (2,4,'Invalid approved sample format'),(1,3,'Unsupported decoder step count'),
])
def test_native_adapter_is_closed_when_startup_fails(server,monkeypatch,tmp_path,channels,steps,message):
    adapter=fake_startup(server,monkeypatch,tmp_path,channels,steps)
    async def run():
        with pytest.raises(RuntimeError,match=message):
            async with server.lifespan(server.app):raise AssertionError('Invalid voice became ready')
    asyncio.run(run())
    assert adapter.closed
    assert server.model is None and server.approved_pcm is None


def test_native_adapter_and_readiness_are_cleared_at_shutdown(server,monkeypatch,tmp_path):
    adapter=fake_startup(server,monkeypatch,tmp_path)
    async def run():
        async with server.lifespan(server.app):
            assert server.health()['ready']
            assert not adapter.closed
    asyncio.run(run())
    assert adapter.closed
    assert not server.health()['ready']


def test_non_ascii_credentials_are_unauthorized(server):
    with pytest.raises(HTTPException) as rejected:server.authenticate('Bearer \u00ff')
    assert rejected.value.status_code==401


def test_startup_memory_release_keeps_live_voice_and_sampler_state(server,monkeypatch):
    calls=[]
    def trim(pad):calls.append(('trim',pad));return 1
    monkeypatch.setattr(server,'os',SimpleNamespace(name='posix'))
    monkeypatch.setattr(server.ctypes,'CDLL',lambda name:SimpleNamespace(malloc_trim=trim))
    monkeypatch.setattr(server.gc,'collect',lambda:calls.append('collect'))
    readings=iter((4096*100,4096*80))
    monkeypatch.setattr(server,'resident_bytes',lambda:next(readings))
    # The allocator must never run Torch code, reseed synthesis, discard
    # prepared conditioning or replace the approved waveform/profile.
    class Sampler:
        def manual_seed(self,*args):raise AssertionError('Allocator changed sampler state')
    monkeypatch.setitem(sys.modules,'torch',Sampler())
    voice=object();profile={'seed':4139};approved=b'\x01\x02';stages={'t3':12.3}
    server.model=voice;server.profile=profile;server.approved_pcm=approved;server.stage_ms=stages
    server.release_startup_allocations()
    assert calls==['collect',('trim',0)]
    assert server.model is voice and server.profile is profile
    assert server.approved_pcm is approved and server.stage_ms is stages
    assert profile=={'seed':4139} and stages=={'t3':12.3}


@pytest.mark.parametrize('failure',[OSError('unavailable library'),AttributeError('missing malloc_trim')])
def test_optional_glibc_trim_cannot_prevent_readiness(server,monkeypatch,tmp_path,failure):
    adapter=fake_startup(server,monkeypatch,tmp_path)
    real_os=server.os
    monkeypatch.setattr(server,'os',SimpleNamespace(name='posix',environ=real_os.environ,getenv=real_os.getenv))
    monkeypatch.setattr(server,'resident_bytes',lambda:None)
    def missing(name):raise failure
    monkeypatch.setattr(server.ctypes,'CDLL',missing)
    async def run():
        async with server.lifespan(server.app):assert server.health()['ready']
    asyncio.run(run())
    assert adapter.closed


@pytest.mark.parametrize('contents,expected', [('123 7 0',7*4096),('invalid',None),('',None)])
def test_resident_memory_measurement_handles_missing_or_invalid_procfs(server,monkeypatch,contents,expected):
    monkeypatch.setattr(server,'Path',lambda path:SimpleNamespace(read_text=lambda:contents))
    monkeypatch.setattr(server,'os',SimpleNamespace(sysconf=lambda name:4096))
    assert server.resident_bytes()==expected


def test_resident_memory_measurement_is_optional_outside_linux(server,monkeypatch):
    def missing(path):raise OSError('procfs unavailable')
    monkeypatch.setattr(server,'Path',missing)
    assert server.resident_bytes() is None
