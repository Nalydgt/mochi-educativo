
import httpx
import pytest

from app import Settings
from native_voice import NativeVoice
from voice_service import VoiceService

PROFILE='a'*64
TOKEN='private-test-key-'*3


def response(pcm=b'\x00\x01'*160,profile=PROFILE,rate='16000'):
    return httpx.Response(200,content=pcm,headers={'Content-Type':'application/octet-stream',
        'X-Mochi-Voice-Profile':profile,'X-Mochi-Sample-Rate':rate})


def test_authenticated_synthesis_uses_exact_profile_and_spanish_text():
    requests=[]
    def handler(request):
        requests.append(request)
        assert request.headers['Authorization']=='Bearer '+TOKEN
        assert request.url.path=='/v1/speech'
        assert PROFILE.encode() in request.content
        return response()
    voice=NativeVoice('http://voice:8767',TOKEN,PROFILE,transport=httpx.MockTransport(handler))
    assert voice.generate('Hola, soy Mochi.')==b'\x00\x01'*160
    assert len(requests)==1


@pytest.mark.parametrize('pcm,profile,rate',[(b'x',PROFILE,'16000'),(b'',PROFILE,'16000'),
    (b'\0\0','b'*64,'16000'),(b'\0\0',PROFILE,'24000')])
def test_invalid_audio_or_changed_speaker_is_rejected(pcm,profile,rate):
    voice=NativeVoice('http://voice:8767',TOKEN,PROFILE,
        transport=httpx.MockTransport(lambda request:response(pcm,profile,rate)))
    with pytest.raises(ValueError):voice.generate('Hola')


def test_readiness_requires_the_selected_speaker():
    voice=NativeVoice('http://voice:8767',TOKEN,PROFILE,transport=httpx.MockTransport(
        lambda request:httpx.Response(200,json={'ready':True,'profile':'b'*64,'sample_rate':16000})))
    assert not voice.ready()


def test_cloud_quota_is_distinct_from_speaker_installation():
    voice=NativeVoice('http://voice:8768',TOKEN,PROFILE,transport=httpx.MockTransport(
        lambda request:httpx.Response(200,json={'ready':True,'profile':PROFILE,'sample_rate':16000,
            'generation_available':False,'quota_retry_seconds':600,'private':'never expose this'})))
    assert voice.ready()
    assert voice.status()=={'ready':True,'generation_available':False,'quota_retry_seconds':600}


class Local:
    def speak(self,text):raise AssertionError('The selected native voice must not fall back to another speaker')


def service(tmp_path,profile=PROFILE,handler=lambda request:response()):
    settings=Settings('d'*40,tmp_path,tmp_path/'voice.onnx',voice_provider='native',
        native_voice_url='http://voice:8767',native_voice_token=TOKEN,native_voice_profile=profile)
    result=VoiceService(settings,Local())
    result.native=NativeVoice(settings.native_voice_url,TOKEN,profile,transport=httpx.MockTransport(handler))
    return result


def test_cache_reuses_only_the_same_text_and_speaker_profile(tmp_path):
    calls=[]
    def handler(request):calls.append(request);return response()
    selected=service(tmp_path,handler=handler)
    assert selected.speak('Hola')==selected.speak('Hola')
    assert len(calls)==1
    other=service(tmp_path,profile='b'*64,handler=lambda request:response(profile='b'*64))
    assert other.native_id!=selected.native_id
    assert other.cache.get(other.native_id,'Hola') is None


def test_native_failure_does_not_change_voice_or_cache_failed_audio(tmp_path):
    selected=service(tmp_path,handler=lambda request:httpx.Response(503))
    with pytest.raises(httpx.HTTPStatusError):selected.speak('Hola')
    assert selected.cache.get(selected.native_id,'Hola') is None
