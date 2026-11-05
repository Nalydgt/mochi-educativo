import json

from hermes_bridge import parse_answer
from prompt_history import PromptHistory


def test_replays_exact_model_json_and_runtime_facts_only_when_history_commits():
    cache=PromptHistory()
    raw=' {"text": "Estoy bien.", "emotion": "happy"} '
    answer=parse_answer(raw)
    message={'role':'user','content':'{"question":"Hola","battery_percent":60}'}
    cache.propose('pet',[],[message],'Hola',answer)
    stored=[{'role':'user','content':'Hola'},{'role':'assistant','content':'Estoy bien.'}]
    replay=cache.for_turn('pet',stored)
    assert replay==[message,{'role':'assistant','content':raw}]
    assert 'battery_percent' not in json.dumps(stored)
    assert 'model_content' not in json.dumps(answer)


def test_aborted_or_edited_history_never_replays_an_uncommitted_answer():
    cache=PromptHistory()
    cache.propose('pet',[],[{'role':'user','content':'Una pregunta'}],'Una pregunta',
        parse_answer('{"text":"Una respuesta.","emotion":"happy"}'))
    assert cache.for_turn('pet',[])==[]
    edited=[{'role':'user','content':'Otra pregunta'}]
    assert cache.for_turn('pet',edited)==edited


def test_prompt_replay_is_bounded_and_isolated_per_device():
    cache=PromptHistory(max_devices=2)
    answer=parse_answer('{"text":"Hola.","emotion":"happy"}')
    for device in ('a','b','c'):
        cache.propose(device,[],[{'role':'user','content':device}],device,answer)
    assert list(cache.entries)==['b','c']
    stored=[{'role':'user','content':'b'},{'role':'assistant','content':'Hola.'}]
    assert cache.for_turn('c',stored)==stored  # different transcript cannot cross devices
    assert cache.for_turn('a',stored)==stored  # evicted entry falls back to durable text


def test_rolling_storage_keeps_an_append_only_prompt_until_bounded_compaction():
    cache=PromptHistory()
    stored=[];previous=[]
    for turn in range(40):
        message={'role':'user','content':json.dumps({'question':str(turn),'battery_percent':90-turn})}
        answer=parse_answer('{"text":"Bien.","emotion":"happy"}')
        messages=cache.for_turn('pet',stored)+[message]
        cache.propose('pet',stored,messages,str(turn),answer)
        stored=(stored+[{'role':'user','content':str(turn)},
            {'role':'assistant','content':'Bien.'}])[-24:]
        replay=cache.for_turn('pet',stored)
        assert len(replay)<=48
        if len(previous)<48:assert replay[:len(previous)]==previous
        else:assert len(replay)==24
        previous=replay


def test_fast_replay_keeps_exact_envelopes_and_compacts_whole_turns_in_batches():
    cache=PromptHistory()
    stored=[];previous=[];compactions=0
    raw=' {"text":"Bien.","emotion":"happy","delegate":false} '
    answer=parse_answer(raw)
    for turn in range(24):
        message={'role':'user','content':json.dumps({'question':str(turn),'shared_memory':'x'*500})}
        messages=cache.for_fast_turn('pet',stored,message,max_characters=3000)
        assert messages[-1]==message
        assert sum(len(m['content']) for m in messages)<=3000
        if previous and messages[:-1]!=previous:
            compactions+=1
            assert messages[:-1]==stored[-12:]
            assert all('shared_memory' not in m['content'] for m in messages[:-1])
        elif previous:
            assert messages[:-1]==previous
            assert messages[-2]['content']==raw
        cache.propose('pet',stored,messages,str(turn),answer)
        stored=(stored+[{'role':'user','content':str(turn)}, {'role':'assistant','content':'Bien.'}])[-24:]
        previous=messages+[{'role':'assistant','content':raw}]
    assert 1<compactions<12


def test_fast_compaction_preserves_current_recall_and_removes_only_whole_old_pairs():
    cache=PromptHistory()
    stored=[{'role':'user','content':'Pregunta.'}, {'role':'assistant','content':'Respuesta.'}]*6
    current={'role':'user','content':'Recuerdo actual completo: '+'z'*100}
    messages=cache.for_fast_turn('pet',stored,current,max_characters=len(current['content'])+24)
    assert messages[-1]==current
    assert messages[:-1]==stored[-2:]
    assert all(m['role']==('user' if i%2==0 else 'assistant') for i,m in enumerate(messages[:-1]))
    assert cache.for_fast_turn('pet',stored,current,max_characters=10)==[current]


def test_fast_replay_rejects_an_uncommitted_or_cross_device_proposal():
    cache=PromptHistory()
    answer=parse_answer('{"text":"Respuesta.","emotion":"idle","delegate":false}')
    cache.propose('a',[],[{'role':'user','content':'Datos privados en RAM'}],'Pregunta.',answer)
    current={'role':'user','content':'Nueva pregunta.'}
    assert cache.for_fast_turn('a',[],current)==[current]
    assert cache.for_fast_turn('b',[],current)==[current]
