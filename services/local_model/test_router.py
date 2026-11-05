import json
from fastapi.testclient import TestClient
import httpx
import pytest

from router import create_app,prepare,SCHEMA,SPOKEN_MARKER,AGENT_MARKER

TOKEN='private-local-test-'*3
HEADERS={'Authorization':'Bearer '+TOKEN}


def test_device_schema_is_applied_during_decoding_without_changing_personality():
    body={'messages':[{'role':'system','content':'Eres Mochi. '+SPOKEN_MARKER+' (lo que dirás).'},
                      {'role':'user','content':'¿Jugamos?'}],'max_tokens':1024,'tools':[{'type':'function'}],
          'tool_choice':'auto','parallel_tool_calls':True}
    result=prepare(body)
    assert result['messages']==body['messages']
    assert 'response_format' not in body
    assert result['response_format']['json_schema']['schema']==SCHEMA
    assert result['max_tokens']==192
    assert result['chat_template_kwargs']['enable_thinking'] is False
    assert result['temperature']==.25
    assert 'tools' not in result and 'tool_choice' not in result
    assert body['tools']


def test_regular_hermes_requests_keep_their_format():
    body={'messages':[{'role':'system','content':'Memoria de la mascota.'}],'max_tokens':512,'tools':[{'type':'function'}]}
    assert prepare(body)=={**body,'model':'mochi-local'}


def test_spoken_agent_preserves_real_tools_without_conflicting_json_grammar():
    tool={'type':'function','function':{'name':'web_search','parameters':{'type':'object'}}}
    body={'messages':[{'role':'system','content':SPOKEN_MARKER+'\n'+AGENT_MARKER},
        {'role':'user','content':'Busca la documentación.'}],'tools':[tool],'tool_choice':'auto',
        'response_format':{'type':'json_object'},'max_tokens':4096}
    result=prepare(body)
    assert result['tools']==[tool] and result['tool_choice']=='auto'
    assert 'response_format' not in result
    assert result['max_tokens']==512 and result['cache_prompt'] is True
    assert result['chat_template_kwargs']['enable_thinking'] is False
    assert 'response_format' in body


def test_user_cannot_opt_in_to_agent_tool_policy():
    body={'messages':[{'role':'system','content':SPOKEN_MARKER},
        {'role':'user','content':AGENT_MARKER}],'tools':[{'type':'function'}]}
    result=prepare(body)
    assert 'tools' not in result
    assert result['response_format']['json_schema']['schema']==SCHEMA


def test_compact_agent_protocol_is_recognized_without_the_legacy_json_marker():
    body={'messages':[{'role':'system','content':AGENT_MARKER}],'tool_choice':'auto'}
    result=prepare(body)
    assert result['cache_prompt'] is True
    assert 'response_format' not in result and 'tool_choice' not in result
    assert result['max_tokens']==512


def test_agent_tool_compaction_preserves_argument_contract_and_original_request():
    import copy
    tool={'type':'function','function':{'name':'terminal','description':'Long guidance. '*200,
        'parameters':{'type':'object','required':['command'],'properties':{
            'command':{'type':'string','description':'Command help. '*200,'minLength':1},
            'mode':{'type':'string','enum':['foreground','background']}}}}}
    original=copy.deepcopy(tool)
    result=prepare({'messages':[{'role':'system','content':SPOKEN_MARKER+' '+AGENT_MARKER}], 'tools':[tool]})
    forwarded=result['tools'][0]
    assert tool==original
    assert forwarded['function']['name']=='terminal'
    schema=forwarded['function']['parameters']
    assert schema['required']==['command']
    assert schema['properties']['mode']['enum']==['foreground','background']
    assert schema['properties']['command']['minLength']==1
    assert len(json.dumps(forwarded))<len(json.dumps(original))/2


def test_user_text_cannot_trigger_a_system_format_change():
    assert 'response_format' not in prepare({'messages':[{'role':'user','content':SPOKEN_MARKER}]})


def test_private_proxy_passes_a_single_request_to_local_inference():
    calls=[]
    def upstream(request):
        calls.append(request)
        assert request.url.host=='model'
        assert request.headers['Authorization']=='Bearer '+TOKEN
        return httpx.Response(200,json={'choices':[{'message':{'content':'{"text":"Hola.","emotion":"happy"}'}}]})
    with TestClient(create_app(TOKEN,httpx.MockTransport(upstream))) as client:
        assert client.post('/v1/chat/completions',json={'messages':[]}).status_code==401
        result=client.post('/v1/chat/completions',headers=HEADERS,json={
            'messages':[{'role':'system','content':SPOKEN_MARKER}]})
        assert result.status_code==200
        assert json.loads(result.json()['choices'][0]['message']['content'])['text']=='Hola.'
        assert len(calls)==1
        assert json.loads(calls[0].content)['response_format']['json_schema']['strict'] is True


def test_sse_is_forwarded_without_accumulating_or_rewriting_tokens():
    data=b'data: {"choices":[]}\n\ndata: [DONE]\n\n'
    with TestClient(create_app(TOKEN,httpx.MockTransport(lambda request:httpx.Response(
            200,content=data,headers={'Content-Type':'text/event-stream'})))) as client:
        result=client.post('/v1/chat/completions',headers=HEADERS,json={'messages':[],'stream':True})
        assert result.content==data
        assert result.headers['content-type'].startswith('text/event-stream')
        assert result.headers['cache-control']=='no-store'


def test_upstream_errors_do_not_expose_content_or_private_headers():
    with TestClient(create_app(TOKEN,httpx.MockTransport(lambda request:httpx.Response(
            400,json={'error':TOKEN})))) as client:
        result=client.post('/v1/chat/completions',headers=HEADERS,json={'messages':[]})
        assert result.status_code==400
        assert TOKEN not in result.text


def test_malformed_request_does_not_reach_model():
    def upstream(request):raise AssertionError('Malformed input reached inference')
    with TestClient(create_app(TOKEN,httpx.MockTransport(upstream))) as client:
        assert client.post('/v1/chat/completions',headers=HEADERS,json={'messages':'bad'}).status_code==422


@pytest.mark.parametrize('body',[
    {'messages':[None]}, {'messages':[1]}, {'messages':['system']},
    {'messages':[],'stream':'false'}, {'messages':[],'stream':1},
])
def test_invalid_message_and_stream_types_are_rejected_before_inference(body):
    def upstream(request):raise AssertionError('Malformed input reached inference')
    with TestClient(create_app(TOKEN,httpx.MockTransport(upstream))) as client:
        assert client.post('/v1/chat/completions',headers=HEADERS,json=body).status_code==422


def test_non_finite_json_is_rejected_before_request_serialization():
    def upstream(request):raise AssertionError('Malformed input reached inference')
    with TestClient(create_app(TOKEN,httpx.MockTransport(upstream))) as client:
        result=client.post('/v1/chat/completions',headers=HEADERS,
            content=b'{"messages": [], "temperature": NaN}')
        assert result.status_code==422


def test_non_ascii_bearer_token_is_unauthorized_instead_of_an_internal_error():
    def upstream(request):raise AssertionError('Unauthorized request reached inference')
    with TestClient(create_app(TOKEN,httpx.MockTransport(upstream))) as client:
        assert client.get('/health',headers={b'Authorization':b'Bearer \xff'}).status_code==401


@pytest.mark.parametrize('data',[[],None,'ready'])
def test_malformed_health_response_is_unavailable(data):
    with TestClient(create_app(TOKEN,httpx.MockTransport(lambda request:httpx.Response(
            200,content=json.dumps(data))))) as client:
        assert client.get('/health',headers=HEADERS).status_code==503


def test_interrupted_non_streaming_response_is_closed_and_reported_unavailable():
    class BrokenStream(httpx.AsyncByteStream):
        closed=False
        async def __aiter__(self):
            yield b'{"choices":'
            raise httpx.ReadError('private upstream details')
        async def aclose(self):self.closed=True
    stream=BrokenStream()
    with TestClient(create_app(TOKEN,httpx.MockTransport(lambda request:httpx.Response(
            200,stream=stream)))) as client:
        result=client.post('/v1/chat/completions',headers=HEADERS,json={'messages':[]})
        assert result.status_code==503
        assert 'private upstream details' not in result.text
        assert stream.closed
