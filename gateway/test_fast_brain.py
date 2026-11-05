"""Real Qwen streaming must overlap synthesis without releasing unvalidated speech."""
import json
import threading

import httpx
import pytest
from fastapi.testclient import TestClient

from app import Settings, TurnTiming, create_app
from fast_brain import ConversationBrain, DelegateToHermes, FastBrain, SCHEMA, literal_wordplay, needs_hermes
from hermes_bridge import HermesUnavailable
from turn_stream import prefetched_reply
from test_gateway import Brain, Speech, TOKEN, HEADERS


PCM = b'\x01\x02' * 1600


def event(content=None, finish=None, **delta):
    if content is not None:
        delta['content'] = content
    return ('data: ' + json.dumps({'choices': [{'delta': delta, 'finish_reason': finish}]}) + '\n\n').encode()


class Stream(httpx.SyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks
        self.closed = False

    def __iter__(self):
        yield from self.chunks()

    def close(self):
        self.closed = True


def fast_with_stream(stream):
    def upstream(request):
        payload = json.loads(request.content)
        assert payload['stream'] is True and payload['cache_prompt'] is True
        assert 'tools' not in payload
        return httpx.Response(200, stream=stream, headers={'Content-Type': 'text/event-stream'})
    return FastBrain('http://localhost', 'x' * 40, '', transport=httpx.MockTransport(upstream))


def test_first_pcm_is_synthesized_before_the_model_finishes_its_answer():
    synthesized = threading.Event()
    rendered = []

    def chunks():
        yield event('{"text":"La nieve se forma en las nubes. ')
        # The model cannot finish until synthesis has actually begun. Waiting
        # for the whole JSON before calling the callback deadlocks this test.
        assert synthesized.wait(3)
        yield event('Los cristales de hielo se agrupan.","emotion":"idle","delegate":false}')
        yield event(finish='stop')
        yield b'data: [DONE]\n\n'

    def render(text):
        rendered.append(text)
        synthesized.set()
        return PCM

    stream = Stream(chunks)
    fast = fast_with_stream(stream)
    try:
        answer, first = prefetched_reply(fast, [{'role': 'user', 'content': '¿Cómo se forma la nieve?'}],
                                         render, TurnTiming())
        assert first == PCM and rendered == ['La nieve se forma en las nubes.']
        assert answer == {'text': 'La nieve se forma en las nubes. Los cristales de hielo se agrupan.', 'emotion': 'idle'}
        assert stream.closed
    finally:
        fast.close()


def test_long_first_sentence_starts_synthesis_at_a_stable_word_cut_before_its_period():
    from turn_stream import speech_parts
    synthesized=threading.Event()
    text='El vapor de agua se enfría y forma diminutas gotas que permanecen suspendidas en el aire hasta formar nubes.'
    expected=speech_parts(text)[0]
    rendered=[]

    def chunks():
        yield event('{"text":"'+text[:70])
        assert synthesized.wait(3)
        yield event(text[70:]+'","emotion":"idle","delegate":false}')
        yield event(finish='stop')
        yield b'data: [DONE]\n\n'

    def render(part):
        rendered.append(part)
        synthesized.set()
        return PCM

    fast=fast_with_stream(Stream(chunks))
    try:
        answer,first=prefetched_reply(fast,[],render,TurnTiming())
        assert first==PCM and answer['text']==text and rendered==[expected]
    finally:
        fast.close()


@pytest.mark.parametrize('failure', ['delegate', 'length', 'missing_done', 'invalid_json', 'tool_call', 'disconnect'])
def test_invalid_or_delegated_stream_never_returns_speculative_speech(failure):
    rendered = []

    def chunks():
        yield event('{"text":"Primera frase provisional. ')
        if failure == 'disconnect':
            raise httpx.ReadError('private upstream detail')
        if failure == 'invalid_json':
            yield event('JSON roto')
        else:
            yield event('Otra frase.","emotion":"idle","delegate":' + ('true' if failure == 'delegate' else 'false') + '}')
        if failure == 'tool_call':
            yield event(tool_calls=[{'id': 'unexpected'}])
        yield event(finish='length' if failure == 'length' else 'stop')
        if failure != 'missing_done':
            yield b'data: [DONE]\n\n'

    stream = Stream(chunks)
    fast = fast_with_stream(stream)
    try:
        with pytest.raises(DelegateToHermes):
            prefetched_reply(fast, [{'role': 'user', 'content': 'Hola'}],
                             lambda text: rendered.append(text) or PCM, TurnTiming())
        assert rendered == ['Primera frase provisional.']
        assert stream.closed
    finally:
        fast.close()


def test_delegation_discards_prepared_fast_audio_and_uses_the_valid_hermes_answer():
    def chunks():
        yield event('{"text":"Una afirmación provisional. ')
        yield event('Sin confirmar.","emotion":"idle","delegate":true}')
        yield event(finish='stop')
        yield b'data: [DONE]\n\n'

    class Hermes:
        def reply_streaming(self, messages, prepare):
            prepare('Respuesta comprobada.')
            return {'text': 'Respuesta comprobada.', 'emotion': 'happy'}

    rendered = []
    fast = fast_with_stream(Stream(chunks))
    brain = ConversationBrain(Hermes(), fast)
    try:
        answer, first = prefetched_reply(brain, [{'role': 'user', 'content': 'Hola'}],
            lambda text: rendered.append(text) or text.encode(), TurnTiming())
        assert answer['text'] == 'Respuesta comprobada.' and first == b'Respuesta comprobada.'
        assert brain.last_route == 'hermes'
        assert rendered == ['Una afirmación provisional.', 'Respuesta comprobada.']
    finally:
        fast.close()


def test_usage_events_and_a_short_answer_without_sentence_break_still_complete():
    def chunks():
        yield b'data: {"choices":[],"usage":{"completion_tokens":8}}\n\n'
        yield event('{"text":"Hola","emotion":"happy","delegate":false}')
        yield event(finish='stop')
        yield b'data: [DONE]\n\n'

    fast = fast_with_stream(Stream(chunks))
    prepared = []
    try:
        assert fast.reply_streaming([], prepared.append) == {'text': 'Hola.', 'emotion': 'happy'}
        assert prepared == ['Hola.']
    finally:
        fast.close()


@pytest.mark.parametrize('question', [
    'Crea una rima sobre las nubes.', 'Créame un cuento breve.',
    'Ponme un ejemplo de una metáfora.', 'Pon un ejemplo de una suma.',
    'Modifica la frase para hacerla más breve.', 'Cambia el poema para que rime.',
    '¿Cuánto tiempo tarda la luz del Sol en llegar?', '¿Qué es el tiempo en física?',
    '¿Qué hora es?', '¿Cuánto tiempo dura una hora?',
])
def test_spoken_creations_examples_and_durations_use_fast_conversation(question):
    assert not needs_hermes(question)


@pytest.mark.parametrize('question', [
    'Crea un cuento y guárdalo en un archivo.', 'Pon un ejemplo y envíamelo por correo.',
    'Modifica la frase de ese archivo.', 'Cambia mi nombre.',
    'Pon una alarma.', 'Crea una carpeta.', '¿Qué tiempo hace?',
    '¿Qué tiempo va a hacer mañana?', '¿Qué tiempo tendremos mañana?',
    'Dime el tiempo.', '¿Cuál es el pronóstico del tiempo?', '¿Qué tiempo en Madrid se espera hoy?',
])
def test_actual_actions_and_weather_still_go_directly_to_hermes(question):
    assert needs_hermes(question)


def test_startup_warms_the_fast_personality_prefix_without_waiting_for_the_tool_agent(tmp_path):
    (tmp_path / 'SOUL.md').write_text('Personalidad sintética de prueba.', encoding='utf-8')
    requests = []

    def upstream(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {
            'content': '{"text":"Hola.","emotion":"happy","delegate":false}'}}]})

    class Hermes:
        def warmup(self):
            raise AssertionError('Fast readiness blocked on the slow tool agent')

    fast = FastBrain('http://localhost', 'x' * 40, tmp_path, transport=httpx.MockTransport(upstream))
    brain = ConversationBrain(Hermes(), fast)
    try:
        brain.warmup()
        assert len(requests) == 1
        payload = requests[0]
        assert payload['cache_prompt'] is True and 'tools' not in payload
        assert payload['messages'][0]['content'] == fast.payload([])['messages'][0]['content']
        assert 'Personalidad sintética de prueba.' in payload['messages'][0]['content']
        assert len(payload['messages']) == 2
    finally:
        fast.close()


def test_failed_fast_warmup_uses_the_gateway_readiness_failure_contract():
    fast = FastBrain('http://localhost', 'x' * 40, '', transport=httpx.MockTransport(
        lambda request: httpx.Response(503)))
    try:
        with pytest.raises(HermesUnavailable, match='could not warm up'):
            fast.warmup()
    finally:
        fast.close()


def test_followup_replays_exact_fast_json_and_context_without_changing_public_answer(tmp_path,monkeypatch):
    payloads=[]
    raw=' {"text": "Hola.", "emotion": "happy", "delegate": false} '

    def upstream(request):
        payloads.append(json.loads(request.content))
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':raw}}]})

    fast=FastBrain('http://localhost','x'*40,'',transport=httpx.MockTransport(upstream))
    monkeypatch.setattr('app.FastBrain',lambda *args:fast)
    class ReadySpeech(Speech):
        def warmup(self):pass
    app=create_app(Settings(TOKEN,tmp_path,tmp_path/'voice.onnx',fast_enabled=True),
                   Brain(),ReadySpeech())
    try:
        with TestClient(app) as client:
            first=client.post('/v1/chat',headers=HEADERS,json={'text':'Hola'})
            assert first.status_code==200 and first.json()=={'text':'Hola.','emotion':'happy'}
            second=client.post('/v1/chat',headers=HEADERS,json={'text':'Cuéntame una rima'})
            assert second.status_code==200 and second.json()==first.json()
        assert len(payloads)==2
        assert payloads[1]['messages'][:2]==payloads[0]['messages']
        assert payloads[1]['messages'][2]=={'role':'assistant','content':raw}
        assert json.loads(payloads[1]['messages'][-1]['content'])['question']=='Cuéntame una rima'
        assert app.state.memory.history('mochi')[-1]=={'role':'assistant','content':'Hola.'}
    finally:
        fast.close()


@pytest.mark.parametrize('question', [
    'Dime una palabra que rime con ventana.', 'Inventa una rima con dragón.',
    'Escríbeme una rima con teléfono.', 'Dame una rima con alarma.',
    'Crea una rima con archivo por favor.',
])
def test_literal_wordplay_stays_local_without_constraining_its_answer(question):
    fast=FastBrain('http://localhost','x'*40,'')
    try:
        assert literal_wordplay(question) and not needs_hermes(question)
        payload=fast.payload([{'role':'user','content':json.dumps({'question':question,'shared_memory':'evidencia'})}])
        schema=payload['response_format']['json_schema']['schema']
        assert schema['properties']['delegate']=={'type':'boolean','const':False}
        assert schema['properties']['text']==SCHEMA['properties']['text']
        assert 'const' not in schema['properties']['text'] and 'enum' not in schema['properties']['text']
        assert SCHEMA['properties']['delegate']=={'type':'boolean'}
    finally:
        fast.close()


@pytest.mark.parametrize('question', [
    'Dime una palabra que rime con mi nombre.', 'Crea una rima con mi apellido.',
    'Dime una palabra que rime con ventana y guarda la respuesta.',
    'Dime una palabra que rime con ventana y envíamela por correo.',
    'Dime una palabra que rime con el nombre que te dije.',
    'Crea una rima con el nombre de mi mascota.',
])
def test_personal_dependencies_and_mixed_actions_keep_delegation_available(question):
    fast=FastBrain('http://localhost','x'*40,'')
    try:
        assert not literal_wordplay(question)
        schema=fast.payload([{'role':'user','content':question}])['response_format']['json_schema']['schema']
        assert schema['properties']['delegate']=={'type':'boolean'}
        if any(word in question for word in ('guarda','envía','dije')):
            assert needs_hermes(question)
    finally:
        fast.close()
