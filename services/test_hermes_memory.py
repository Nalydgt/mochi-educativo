"""Run plugin input contracts with doubles for the optional Hermes installation."""
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType

import pytest


@pytest.fixture
def provider(monkeypatch):
    package=ModuleType('agent')
    memory_provider=ModuleType('agent.memory_provider')
    memory_provider.MemoryProvider=object
    memory_provider.spawn_context_thread=lambda *args,**kwargs:None
    monkeypatch.setitem(sys.modules,'agent',package)
    monkeypatch.setitem(sys.modules,'agent.memory_provider',memory_provider)
    spec=importlib.util.spec_from_file_location('mochi_memory_provider',Path(__file__).parent/'hermes_memory'/'__init__.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    class Store:
        def __init__(self):self.context_calls=[];self.search_calls=[]
        def context(self,device,query):
            assert isinstance(device,str) and isinstance(query,str)
            self.context_calls.append((device,query))
            return 'saved evidence'
        def search(self,device,query,limit):
            self.search_calls.append((device,query,limit))
            return [{'question':'Previous conversation'}]
    instance=module.MochiMemoryProvider()
    instance.device='configured-device'
    instance.store=Store()
    return instance


@pytest.mark.parametrize('exchange',[[],None,False,23,'bad',{},
    {'device':[]},{'device':None},{'device':23},{'device':''},
    {'device':'x'*49},{'device':'invalid device'},{'device':'..'},{'device':'M\u00e1laga'}])
def test_malformed_exchange_falls_back_to_configured_device(provider,exchange):
    message=json.dumps({'mochi_exchange':exchange,'question':'Remember the earlier conversation'})
    provider.on_turn_start(1,message)
    assert provider.turn_device=='configured-device'
    assert 'saved evidence' in provider.prefetch(message)
    assert provider.store.context_calls==[('configured-device','Remember the earlier conversation')]


@pytest.mark.parametrize('question',[None,[],{},23,False])
def test_non_text_question_falls_back_to_original_message(provider,question):
    message=json.dumps({'question':question})
    provider.prefetch(message)
    assert provider.store.context_calls==[('configured-device',message)]


def test_valid_gateway_device_is_kept_for_recall_and_tool_search(provider):
    message=json.dumps({'mochi_exchange':{'device':'mochi-other_2','id':'turn-1'},'question':'Earlier topic'})
    provider.on_turn_start(1,message)
    provider.prefetch(message)
    result=json.loads(provider.handle_tool_call('mochi_history_search',{'query':'Earlier','limit':4}))
    assert provider.store.context_calls==[('mochi-other_2','Earlier topic')]
    assert provider.store.search_calls==[('mochi-other_2','Earlier',4)]
    assert result['exchanges']


def test_shared_memory_is_not_injected_again_and_keeps_device(provider):
    message=json.dumps({'mochi_exchange':{'device':'mochi-other'},'shared_memory':{'facts':[]}})
    assert provider.prefetch(message)==''
    assert provider.turn_device=='mochi-other'
    assert not provider.store.context_calls


@pytest.mark.parametrize('args',[None,[],{'query':None},{'query':[]},{'query':23},
    {'query':'topic','limit':None},{'query':'topic','limit':True},
    {'query':'topic','limit':0},{'query':'topic','limit':21},{'query':'topic','limit':'8'}])
def test_invalid_tool_arguments_are_rejected_before_search(provider,args):
    with pytest.raises(ValueError):provider.handle_tool_call('mochi_history_search',args)
    assert not provider.store.search_calls


def test_native_text_and_tool_defaults_use_configured_device(provider):
    provider.prefetch('Remember this topic')
    provider.handle_tool_call('mochi_history_search',{'query':'topic'})
    assert provider.store.context_calls==[('configured-device','Remember this topic')]
    assert provider.store.search_calls==[('configured-device','topic',8)]
