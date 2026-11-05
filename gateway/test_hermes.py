import httpx
import pytest

from hermes_bridge import HermesBrain, HermesUnavailable, first_sentence


def test_routes_to_mochi_profile_with_its_key():
    calls = []
    def handler(request):
        calls.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "mochi"}]})
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {
            "content": '{"text":"Hola, Dylan.","emotion":"happy"}'}}]})
    brain = HermesBrain("http://hermes:30432", "s" * 40, transport=httpx.MockTransport(handler))
    assert brain.ready()
    assert brain.reply([{"role": "user", "content": "Hola"}])["emotion"] == "happy"
    assert str(calls[-1].url) == "http://hermes:30432/p/mochi/v1/chat/completions"
    assert calls[-1].headers["authorization"] == "Bearer " + "s" * 40


@pytest.mark.parametrize('content',[
    '{"text":"Lo he comprobado.","emotion":"curious","continuation":"La fuente confirma el dato."}',
    'curious|Lo he comprobado. La fuente confirma el dato.'])
def test_agent_speech_waits_for_hermes_final_result_instead_of_speaking_tool_commentary(content):
    import json
    from hermes_bridge import AGENT_MARKER
    def handler(request):
        body=json.loads(request.content)
        assert body['stream'] is False
        assert AGENT_MARKER in body['messages'][0]['content']
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{
            'content':content}}]})
    brain=HermesBrain('http://hermes:30432','s'*40,transport=httpx.MockTransport(handler),agent_mode=True)
    prepared=[]
    answer=brain.reply_streaming([{'role':'user','content':'Busca ese dato.'}],prepared.append)
    assert answer['text']=='Lo he comprobado. La fuente confirma el dato.'
    assert prepared==['Lo he comprobado.']


def test_unexecuted_tool_call_is_never_a_completed_spoken_answer():
    transport=httpx.MockTransport(lambda request:httpx.Response(200,json={'choices':[
        {'finish_reason':'stop','message':{'content':'{"text":"Hecho.","emotion":"happy"}',
            'tool_calls':[{'type':'function','function':{'name':'web_search','arguments':'{}'}}]}}]}))
    brain=HermesBrain('http://hermes:30432','s'*40,transport=transport,agent_mode=True)
    prepared=[]
    with pytest.raises(HermesUnavailable):brain.reply_streaming([],prepared.append)
    assert not prepared


def test_agent_accepts_final_natural_speech_without_another_model_call():
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{
            'content':'Hola, **soy Mochi**. Consulta [la documentación](https://docs.python.org/).'}}]})
    brain=HermesBrain('http://hermes:30432','s'*40,transport=httpx.MockTransport(handler),agent_mode=True)
    answer=brain.reply([])
    assert answer=={'text':'Hola, soy Mochi. Consulta la documentación.','emotion':'idle'}
    assert len(calls)==1


def test_compact_agent_emotion_is_parsed_without_reading_its_tag():
    from hermes_bridge import parse_agent_answer
    answer=parse_agent_answer('happy|Hola, estoy contigo.')
    assert answer=={'text':'Hola, estoy contigo.','emotion':'happy'}
    assert answer.model_content=='happy|Hola, estoy contigo.'


@pytest.mark.parametrize('content',[
    'happy|Hola, **soy Mochi**. 😊',
    '{"text":"Hola, **soy Mochi**. 😊","emotion":"happy"}'])
def test_all_final_formats_clean_emojis_and_markdown_identically(content):
    from hermes_bridge import parse_agent_answer
    answer=parse_agent_answer(content)
    assert answer['text']=='Hola, soy Mochi.'
    assert answer.model_content==content
    assert parse_agent_answer('idle|Hay 20 °C.')['text']=='Hay 20 °C.'


def test_legacy_json_cannot_bypass_unexecuted_tool_payload_rejection():
    from hermes_bridge import parse_agent_answer
    with pytest.raises(ValueError):
        parse_agent_answer('{"text":"terminal\\n{\\"command\\":\\"print(1)\\"}","emotion":"idle"}')


@pytest.mark.parametrize('content',['{"text":"Hecho', '<tool_call>{"name":"terminal"}</tool_call>',
    '<think>Private reasoning</think>Hecho.', '```python\nprint(1)\n```', '```python\nprint(1)',
    'unknown_state|Hola.', 'happy|', '',
    'terminal\n{"command":"python -c \\\"print(1)\\\""}',
    'idle|web_search({"query":"MicroPython"})'])
def test_agent_never_reads_damaged_json_tool_markup_or_code_as_speech(content):
    transport=httpx.MockTransport(lambda request:httpx.Response(200,json={'choices':[
        {'finish_reason':'stop','message':{'content':content}}]}))
    brain=HermesBrain('http://hermes:30432','s'*40,transport=transport,agent_mode=True)
    with pytest.raises(HermesUnavailable):brain.reply([])


def test_cold_prefix_warmup_retries_once_but_spoken_turns_do_not():
    calls=[]
    def handler(request):
        calls.append(request)
        if len(calls)==1:return httpx.Response(503)
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{
            'content':'{"text":"Hola.","emotion":"happy"}'}}]})
    brain=HermesBrain('http://hermes:30432','s'*40,transport=httpx.MockTransport(handler))
    brain.warmup()
    assert len(calls)==2
    assert calls[0].content==calls[1].content
    failed=[]
    def unavailable(request):
        failed.append(request);return httpx.Response(503)
    brain=HermesBrain('http://hermes:30432','s'*40,transport=httpx.MockTransport(unavailable))
    with pytest.raises(HermesUnavailable):brain.warmup()
    assert len(failed)==2
    with pytest.raises(HermesUnavailable):brain.reply([])
    assert len(failed)==3


@pytest.mark.parametrize("status", [401, 404, 503])
def test_does_not_fall_back_to_default_profile(status):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"error": "private diagnostics"})
    brain = HermesBrain("http://hermes:30432", "s" * 40, transport=httpx.MockTransport(handler))
    with pytest.raises(HermesUnavailable, match="Mochi profile"):
        brain.reply([{"role": "user", "content": "Hola"}])
    assert len(calls) == 1
    assert "/p/mochi/" in str(calls[0].url)


def test_http_200_with_error_finish_is_not_a_successful_turn():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"choices": [
        {"finish_reason": "error", "message": {"content": "upstream credentials"}}]}))
    brain = HermesBrain("http://hermes:30432", "s" * 40, transport=transport)
    with pytest.raises(HermesUnavailable):
        brain.reply([])


def test_short_first_sentence_preserves_the_full_continuation_for_existing_clients():
    transport=httpx.MockTransport(lambda request:httpx.Response(200,json={'choices':[
        {'finish_reason':'stop','message':{'content':
            '{"text":"Estoy muy contento.","emotion":"happy","continuation":"Podemos jugar a memoria cuando quieras."}'}}]}))
    brain=HermesBrain('http://hermes:30432','s'*40,transport=transport)
    assert brain.reply([])=={'text':'Estoy muy contento. Podemos jugar a memoria cuando quieras.','emotion':'happy'}


def test_partial_json_never_exposes_an_unfinished_or_escaped_string():
    assert first_sentence('{"text":"Hola') is None
    assert first_sentence('{"text":"Hola\\"') is None
    assert first_sentence('{"continuation":"Hola."}') is None
    assert first_sentence('{"text":"Respuesta sin terminar') is None
    assert first_sentence('{"text":"Estoy feliz.",')=='Estoy feliz.'
    assert first_sentence('{"text":"Soy Mochi",')=='Soy Mochi.'
    assert first_sentence('{"text":"Estoy muy feliz. ¿Y tú?",')=='Estoy muy feliz.'
    assert first_sentence('{"text":"Tengo 3.14 puntos. Podemos seguir')=='Tengo 3.14 puntos.'
    assert first_sentence('{"text":"Tengo 3.') is None


@pytest.mark.parametrize('text', [
    'El vapor de agua se enfría y forma diminutas gotas que permanecen suspendidas en el aire hasta formar nubes.',
    'El dato "3.14" sirve para explicar una constante matemática sin cortar sus cifras ni perder ninguna palabra.',
    'Al enfriarse, el vapor de agua se convierte en pequeñas gotas que flotan en la atmósfera y forman nubes visibles.',
    'Una explicación de más de ciento ochenta caracteres permite comprobar que la primera parte queda preparada mucho antes de terminar toda la frase aunque todavía no exista un punto que indique su final en el texto generado.',
])
def test_every_open_json_prefix_prepares_only_the_final_stable_speech_fragment(text):
    import json
    from turn_stream import speech_parts
    encoded=json.dumps(text,ensure_ascii=True)
    expected=speech_parts(text)[0]
    prepared=[]
    for cut in range(1,len(encoded)+1):
        candidate=first_sentence('{"text":'+encoded[:cut])
        if candidate is not None:
            assert candidate==expected
            prepared.append(cut)
    assert prepared and prepared[0]<len(encoded)-20


@pytest.mark.parametrize('suffix',['\\', '\\u', '\\u00', '\\u00f', '\\q'])
def test_even_a_long_prefix_does_not_complete_a_damaged_json_escape(suffix):
    prefix='Esta frase tiene suficientes palabras para producir una primera parte estable '
    assert first_sentence('{"text":"'+prefix+suffix) is None


def test_hermes_stream_prepares_a_complete_sentence_before_the_last_tokens():
    import json
    prepared=[]
    def event(delta=None,finish=None):
        return ('data: '+json.dumps({'choices':[{'delta':delta or {},'finish_reason':finish}]})+'\n\n').encode()
    class Stream(httpx.SyncByteStream):
        def __iter__(self):
            yield event({'content':'{"text":"Estoy feliz. '})
            assert prepared==['Estoy feliz.']
            yield event({'content':'¿Jugamos?","emotion":"happy","continuation":""}'})
            yield event(finish='stop')
            yield b'data: [DONE]\n\n'
    def handler(request):
        assert json.loads(request.content)['stream'] is True
        return httpx.Response(200,stream=Stream())
    brain=HermesBrain('http://hermes:30432','s'*40,transport=httpx.MockTransport(handler))
    assert brain.reply_streaming([],prepared.append)=={'text':'Estoy feliz. ¿Jugamos?','emotion':'happy'}


@pytest.mark.parametrize('tail',[b'',b'data: [DONE]\n\n',
    b'data: {"choices":[{"delta":{},"finish_reason":"error"}]}\n\ndata: [DONE]\n\n'])
def test_stream_without_successful_stop_is_rejected_even_if_text_was_prepared(tail):
    data=b'data: {"choices":[{"delta":{"content":"{\\"text\\":\\"Hola.\\",\\"emotion\\":\\"happy\\"}"}}]}\n\n'+tail
    brain=HermesBrain('http://hermes:30432','s'*40,transport=httpx.MockTransport(
        lambda request:httpx.Response(200,content=data)))
    with pytest.raises(HermesUnavailable):brain.reply_streaming([],lambda text:None)
