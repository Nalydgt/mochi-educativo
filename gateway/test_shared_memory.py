import asyncio
import json
import sqlite3

import httpx
import pytest
from fastapi.testclient import TestClient

from app import Settings,create_app
from fast_brain import FastBrain,ConversationBrain,needs_hermes
from memory_store import Memory
from memory_review import MemoryReviewer
from test_gateway import Brain,Speech,TOKEN,HEADERS


def test_migration_keeps_all_rows_and_unpaired_question_across_restarts(tmp_path):
    path=tmp_path/'memory.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY,device TEXT,role TEXT,content TEXT)')
        db.executemany('INSERT INTO messages(device,role,content) VALUES(?,?,?)',[
            ('a','user','Mi primer dato.'),('a','assistant','Respuesta.'),('b','user','Interrumpida.')])
    store=Memory(path,recover=True)
    assert store.history('a')==[{'role':'user','content':'Mi primer dato.'},{'role':'assistant','content':'Respuesta.'}]
    assert store.get('legacy-3')['delivery']=='incomplete'
    Memory(path,recover=True)
    with store.connect() as db:
        assert db.execute('SELECT count(*) FROM exchanges').fetchone()[0]==2
        assert db.execute('SELECT count(*) FROM messages').fetchone()[0]==3
    for i in range(120):store.append_turn('a',f'Pregunta {i}',f'Respuesta {i}')
    assert store.search('a','primer')[0]['question']=='Mi primer dato.'


def test_retry_never_reexecutes_actions_or_invents_success_after_unknown_outcome(tmp_path):
    brain=Brain();app=create_app(Settings(TOKEN,tmp_path,tmp_path/'voice'),brain,Speech())
    client=TestClient(app)
    body={'text':'Guarda que mi color es turquesa.','exchange_id':'same-1'}
    assert client.post('/v1/chat',headers=HEADERS,json=body).status_code==200
    assert client.post('/v1/chat',headers=HEADERS,json=body).status_code==200
    assert len(brain.calls)==1
    assert client.post('/v1/chat',headers=HEADERS,json={**body,'text':'Otra acción'}).status_code==409
    brain.fail=True
    assert client.post('/v1/chat',headers=HEADERS,json={**body,'exchange_id':'failed-1'}).status_code==503
    assert client.post('/v1/chat',headers=HEADERS,json={**body,'exchange_id':'failed-1'}).status_code==409
    assert app.state.memory.get('failed-1')['delivery']=='incomplete'


def test_pcm_retry_uses_same_answer_and_checks_recording_identity(tmp_path):
    brain=Brain();app=create_app(Settings(TOKEN,tmp_path,tmp_path/'voice'),brain,Speech());client=TestClient(app)
    headers={**HEADERS,'Content-Type':'application/octet-stream','X-Mochi-Turn-ID':'voice-1','X-Mochi-Stream':'pcm16'}
    data=b'\x00\x01'*8000
    assert client.post('/v1/turn',headers=headers,content=data).status_code==200
    assert client.post('/v1/turn',headers=headers,content=data).status_code==200
    assert len(brain.calls)==1
    assert client.post('/v1/turn',headers=headers,content=b'\x02\x03'*8000).status_code==409


def test_review_failure_retains_pending_and_correction_cannot_be_overwritten_by_old_batch(tmp_path):
    store=Memory(tmp_path/'memory.sqlite3')
    first=store.append_turn('mochi','Mi color es azul.','Entendido.')
    rows=store.pending()
    store.review_failed(rows)
    assert 'azul' in store.context('mochi','color')
    last=store.append_turn('mochi','Corrijo mi color: es verde.','Entendido.')
    store.review_commit([store.get(last)],[{'key':'user.color','content':'Verde','source':last}])
    store.review_commit(rows,[{'key':'user.color','content':'Azul','source':first}])
    assert store.facts('mochi')[0]['content']=='Verde'
    with pytest.raises(ValueError):store.review_commit(rows,[{'key':'user.color','content':'Rojo','source':'invented'}])


def test_confirmed_native_forgetting_cannot_be_undone_by_an_old_review(tmp_path):
    store=Memory(tmp_path/'memory.sqlite3')
    identifier=store.append_turn('mochi','Mi color es azul.','Vale.')
    rows=store.pending();updates=[{'key':'user.color','content':'Mi color es azul.','source':identifier}]
    store.review_commit(rows,updates)
    store.invalidate_native('Mi color es azul.')
    store.review_commit(rows,updates)
    assert store.facts('mochi')[0]['content']==''


def test_pending_backlog_still_supplies_new_information_and_accent_insensitive_search(tmp_path):
    store=Memory(tmp_path/'memory.sqlite3')
    for i in range(40):store.append_turn('mochi',f'Dato antiguo {i}.','Vale.')
    store.append_turn('mochi','Mi dirección de prueba está en Málaga.','Entendido.')
    assert 'Málaga' in store.context('mochi','direccion')
    assert store.search('mochi','direccion')[0]['question'].endswith('Málaga.')


def test_review_cannot_attach_an_old_fact_to_unrelated_new_evidence(tmp_path):
    store=Memory(tmp_path/'memory.sqlite3')
    identifier=store.append_turn('mochi','Mi planta se llama Bruma.','Vale.')
    with pytest.raises(ValueError,match='direct evidence'):
        store.review_commit(store.pending(),[{'key':'user.favorite_drink','content':'Café','source':identifier}])
    assert store.pending() and not store.facts('mochi')


def test_new_conversation_cancels_review_without_acknowledging_any_evidence(tmp_path):
    async def run():
        store=Memory(tmp_path/'memory.sqlite3');store.append_turn('mochi','Me gusta el té.','Vale.')
        entered=asyncio.Event();cancelled=asyncio.Event()
        async def handler(request):
            payload=json.loads(request.content)
            assert 'tools' not in payload and 'response_format' in payload
            assert 'assistant' not in json.loads(payload['messages'][-1]['content'])['evidence'][0]
            entered.set()
            try:await asyncio.Event().wait()
            except asyncio.CancelledError:cancelled.set();raise
        reviewer=MemoryReviewer(store,'http://localhost','k'*40,transport=httpx.MockTransport(handler))
        reviewer.task=asyncio.create_task(reviewer.review_once())
        await entered.wait()
        async with reviewer.foreground():assert cancelled.is_set()
        assert len(store.pending())==1 and not store.facts('mochi')
    asyncio.run(run())


def test_long_review_batches_fit_compact_context_without_dropping_pending_turns(tmp_path):
    async def run():
        store=Memory(tmp_path/'memory.sqlite3')
        for index in range(12):store.append_turn('mochi',str(index)+' dato'*399,'Entendido.')
        sizes=[]
        async def handler(request):
            payload=json.loads(request.content);recall=payload['messages'][-1]['content'];sizes.append(len(recall))
            assert len(recall)<=12000
            return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'{"facts":[]}'}}]})
        reviewer=MemoryReviewer(store,'http://localhost','k'*40,transport=httpx.MockTransport(handler))
        assert await reviewer.review_once()
        assert sizes and 0<len(store.pending())<12
        with store.connect() as db:assert db.execute('SELECT count(*) FROM exchanges').fetchone()[0]==12
    asyncio.run(run())


@pytest.mark.parametrize('question',['Busca una noticia de hoy','Guarda mi nombre','Recuerda lo que dijimos ayer',
    'Apaga la luz','Envía un mensaje','Crea un archivo','Comprueba el precio actual','Pon una alarma','Olvida mi dirección'])
def test_tool_intents_go_to_hermes(question):assert needs_hermes(question)


def test_uncertain_direct_answer_is_delegated_without_speaking_a_claim(tmp_path):
    def handler(request):
        body=json.loads(request.content)
        assert 'tools' not in body
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'text':'','emotion':'idle','delegate':True})}}]})
    fast=FastBrain('http://localhost','x'*40,'',transport=httpx.MockTransport(handler));hermes=Brain()
    router=ConversationBrain(hermes,fast)
    assert router.reply([{'role':'user','content':'Pregunta difícil'}])['text']=='Hola, me alegra verte.'
    assert router.last_route=='hermes' and len(hermes.calls)==1


@pytest.mark.parametrize('payload', [[], None, {'choices': [None]},
    {'choices': [{'finish_reason': 'stop', 'message': {'content': '[]'}}]},
    {'choices': [{'finish_reason': 'stop', 'message': {'content': '{"delegate":false,"text":null,"emotion":"idle"}'}}]}])
def test_malformed_fast_reply_delegates_to_hermes(payload):
    fast = FastBrain('http://localhost', 'x'*40, '', transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=payload)))
    hermes = Brain()
    router = ConversationBrain(hermes, fast)
    assert router.reply([{'role': 'user', 'content': 'Hola'}])['text'] == 'Hola, me alegra verte.'
    assert router.last_route == 'hermes' and len(hermes.calls) == 1
    router.close()


def test_context_keeps_recent_pending_records_within_compact_budget(tmp_path):
    store = Memory(tmp_path / 'memory.sqlite3')
    for index in range(20):
        store.append_turn('mochi', f'Dato {index}: Málaga y té.', 'Entendido.')
    context = store.context('mochi', 'Dato', max_chars=600)
    assert len(context) <= 600
    data = json.loads(context)
    assert data['pending'][-1]['question'] == 'Dato 19: Málaga y té.'
    assert not data['older_matches']


def test_native_voice_warmup_loads_only_asr(tmp_path):
    from voice_service import VoiceService
    class Local:
        def warmup(self):raise AssertionError('Retired synthesizer loaded')
        def warmup_transcriber(self):self.loaded=True
    local=Local();settings=Settings(TOKEN,tmp_path,tmp_path/'voice',voice_provider='native',
        native_voice_url='http://localhost:8775',native_voice_token='v'*40,native_voice_profile='a'*64)
    VoiceService(settings,local).warmup()
    assert local.loaded
