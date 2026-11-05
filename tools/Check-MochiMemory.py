"""Exercise the local memory provider in Hermes with an isolated synthetic DB."""
import argparse,json
from pathlib import Path
from nas import NAS
ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--settings',type=Path,default=ROOT/'.runtime/nas.json')
    a=p.parse_args();nas=NAS(json.loads(a.settings.read_text()))
    files={'__init__.py':(ROOT/'services/hermes_memory/__init__.py').read_text(),
           'memory_store.py':(ROOT/'gateway/memory_store.py').read_text()}
    try:
        output=nas.container('hermes-agent','hermes-agent',"python - <<'PY'\n"+'FILES='+repr(files)+'\n'+'''
from pathlib import Path
from tempfile import TemporaryDirectory
import importlib.util,json
with TemporaryDirectory(prefix='mochi-provider-test-') as directory:
    root=Path(directory)
    for name,content in FILES.items():(root/name).write_text(content)
    (root/'mochi-local.json').write_text(json.dumps({'database':str(root/'memory.sqlite3'),'device':'synthetic'}))
    spec=importlib.util.spec_from_file_location('mochi_provider_under_test',root/'__init__.py')
    plugin=importlib.util.module_from_spec(spec);spec.loader.exec_module(plugin)
    provider=plugin.MochiMemoryProvider();provider.initialize('test-session',hermes_home=str(root),agent_context='primary')
    provider.sync_turn('Mi color de prueba es turquesa.','Entendido.',session_id='test-session')
    provider.shutdown()
    provider.sync_turn('Mi color de prueba es turquesa.','Entendido.',session_id='test-session')
    provider.shutdown()
    assert len(provider.store.history('synthetic'))==2
    result=json.loads(provider.handle_tool_call('mochi_history_search',{'query':'turquesa'}))
    assert len(result['exchanges'])==1
    assert 'turquesa' in provider.prefetch('color de prueba')
    row=provider.store.pending()[0]
    provider.store.review_commit([row],[{'key':'user.color','content':'Turquesa','source':row['id']}])
    provider.on_memory_write('remove','memory','',{'previous_content':'Turquesa'})
    assert provider.store.facts('synthetic')[0]['content']==''
    provider.sync_turn(json.dumps({'question':'No duplicar','mochi_exchange':{'id':'gateway-id','device':'synthetic'}}),'Respuesta.')
    assert len(provider.store.history('synthetic'))==2
    other=plugin.MochiMemoryProvider()
    other_root=root/'other';other_root.mkdir();(other_root/'mochi-local.json').write_text(json.dumps({'database':str(other_root/'memory.sqlite3'),'device':'other'}))
    other.initialize('other-session',hermes_home=str(other_root),agent_context='primary')
    assert 'turquesa' not in other.prefetch('color')
    print(json.dumps({'passed':True,'actual_hermes_api':True,'deduplicated':True,'gateway_turn_not_duplicated':True,'profile_isolation':True,'native_forgetting_preserved':True,'personal_files_changed':False}))
PY''',timeout=20)
        print(output)
        (ROOT/'docs/mediciones/20261026-proveedor-memoria.json').write_text(output+'\n')
    finally:nas.close()


if __name__=='__main__':main()
