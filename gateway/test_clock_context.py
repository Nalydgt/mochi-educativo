from datetime import datetime,timezone
import json

from fastapi.testclient import TestClient
import pytest

from app import Settings,create_app
from clock_context import ClockService
from device_context import DeviceContext,user_turn_message
from test_gateway import Brain,Speech,TOKEN,HEADERS

NOW=datetime(2026,10,24,22,30,tzinfo=timezone.utc)


def test_clock_uses_configured_local_day_across_utc_midnight():
    clock=ClockService(clock=lambda:NOW)
    assert clock.answer('¿Qué día es hoy?')['text']=='Hoy es domingo, 25 de octubre de 2026.'
    assert clock.answer('¿Qué día será mañana?')['text']=='Mañana será lunes, 26 de octubre de 2026.'
    assert clock.answer('¿Qué día era ayer?')['text']=='Ayer fue sábado, 24 de octubre de 2026.'
    assert clock.context('¿Qué día es hoy?')['datetime']=='2026-10-25T00:30:00+02:00'


def test_hour_observes_dst_fallback_and_refreshes_every_turn():
    now=[datetime(2026,10,25,0,30,tzinfo=timezone.utc)]
    clock=ClockService(clock=lambda:now[0])
    assert clock.answer('¿Qué hora es?')['text']=='Son las 02:30.'
    assert clock.context('hora')['datetime'].endswith('+02:00')
    now[0]=datetime(2026,10,25,1,30,tzinfo=timezone.utc)
    assert clock.answer('¿Qué hora es?')['text']=='Son las 02:30.'
    assert clock.context('hora')['datetime'].endswith('+01:00')


@pytest.mark.parametrize('question',[
    '¿Qué día es mejor para plantar tomates?',
    '¿Qué día es hoy y por qué llueve?',
    'Busca qué día es fiesta en Madrid.',
    'Si hoy fuera lunes, ¿qué día sería mañana?',
    '¿Cuánto es siete más ocho?',
    '¿Qué tiempo hace hoy?'])
def test_clock_does_not_replace_other_intents_or_multi_part_requests(question):
    assert ClockService(clock=lambda:NOW).answer(question) is None


def test_question_remains_last_without_imperative_care_instructions():
    ctx=DeviceContext(pet={'energy':10,'satiety':90,'mood':60,'curiosity':50})
    message=user_turn_message('¿Cuánto es siete más ocho?',ctx)
    payload=json.loads(message['content'])
    assert list(payload)[-1]=='question'
    assert 'care_observations' not in payload
    assert 'pet' not in payload['mochi_device_context']
    assert payload['question']=='¿Cuánto es siete más ocho?'


def test_retired_care_context_is_ignored_and_current_device_facts_remain_authoritative():
    ctx=DeviceContext(name='Luna',pet={'energy':10,'satiety':90,'mood':60,'curiosity':50},battery_percent=28)
    payload=json.loads(user_turn_message('¿Qué tal estás?',ctx)['content'])
    assert 'care_facts' not in payload
    assert 'pet' not in payload['mochi_device_context']
    assert 'pet' not in ctx.model_dump()
    assert 'battery_percent' not in payload['mochi_device_context']
    assert ctx.answer('¿Cómo estás de energía y qué te ayuda a recuperarla?') is None
    assert ctx.answer('¿Tienes hambre?') is None
    assert ctx.answer('¿Cómo te llamas ahora?')['text']=='Me llamo Luna.'
    assert '28' in ctx.answer('¿Cuánta batería te queda?')['text']
    assert ctx.answer('¿Qué día es hoy?') is None
    assert ctx.answer('¿Cómo te llamas y qué puedes hacer?') is None
    assert ctx.answer('¿Qué es la energía?') is None


def test_unknown_battery_is_never_made_up():
    assert DeviceContext().answer('¿Cuánta batería tienes?')['text']=='Ahora no tengo una lectura de batería.'


def test_real_regression_date_ignores_tired_pet_and_preserves_followup_history(tmp_path):
    class Local(Speech):
        def transcribe(self,pcm):return '¿Qué día es hoy?'
    brain=Brain()
    app=create_app(Settings(TOKEN,tmp_path,tmp_path/'voice.onnx'),brain,Local(),clock=ClockService(clock=lambda:NOW))
    app.state.memory.append_turn('pet','¿Cómo estás?','Mochi está cansado, necesita descansar.')
    client=TestClient(app)
    context={'pet':{'energy':10,'satiety':90,'mood':60,'curiosity':50}}
    response=client.post('/v1/turn',content=b'\x01\x02'*3200,headers={**HEADERS,
        'Content-Type':'application/octet-stream','X-Device-ID':'pet','X-Mochi-Context':json.dumps(context)})
    assert response.status_code==200 and not brain.calls
    history=app.state.memory.history('pet')
    assert history[-2]['content']=='¿Qué día es hoy?'
    assert history[-1]['content']=='Hoy es domingo, 25 de octubre de 2026.'
    response=client.post('/v1/chat',headers=HEADERS,json={'text':'¿Cuánto es siete más ocho?','device_id':'pet'})
    assert response.status_code==200
    assert any('Hoy es domingo' in m['content'] for m in brain.calls[-1])
    assert not any('care_observations' in m['content'] for m in brain.calls[-1])


def test_personal_name_and_both_api_paths_use_trusted_clock(tmp_path):
    brain=Brain();clock=ClockService(clock=lambda:NOW)
    client=TestClient(create_app(Settings(TOKEN,tmp_path,tmp_path/'voice.onnx'),brain,Speech(),clock=clock))
    assert clock.answer('Luna, ¿qué fecha es hoy?',name='Luna')
    response=client.post('/v1/chat',headers=HEADERS,json={'text':'Dime la hora por favor'})
    assert response.status_code==200 and response.json()['text']=='Son las 00:30.'
    assert not brain.calls
