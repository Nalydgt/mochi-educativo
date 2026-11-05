from pathlib import Path

from spoken_identity import compact_messages
import spoken_identity
import router


def test_compacts_only_exact_known_identity_and_preserves_memories_and_other_rules():
    original='Full known identity.';short='Short identity.'
    messages=[{'role':'system','content':original+'\nVerified saved memory: blue.\nAPI contract.'},
        {'role':'user','content':original}]
    compact=compact_messages(messages,original,short)
    assert compact[0]['content']==short+'\nVerified saved memory: blue.\nAPI contract.'
    assert compact[1]==messages[1] and messages[0]['content'].startswith(original)
    assert compact_messages(messages,'Changed full identity.',short)==messages
    assert compact_messages(messages,'',short)==messages


def test_voice_identity_is_smaller_and_retains_personality_memory_and_current_state_rules():
    root=Path(__file__).resolve().parents[2]/'profiles/mochi'
    full=(root/'SOUL.md').read_text(encoding='utf-8')
    short=(root/'SOUL-VOICE.md').read_text(encoding='utf-8')
    assert len(short)<len(full)/2
    for required in ('Mochi','recuerdos','firmware','criterio','discrepar','ausencias','disculpas'):
        assert required in short


def test_router_reduces_only_the_spoken_contract(monkeypatch):
    monkeypatch.setattr(router,'IDENTITIES',('Full known identity.','Short identity.'))
    ordinary={'messages':[{'role':'system','content':'Full known identity.'}]}
    assert router.prepare(ordinary)['messages']==ordinary['messages']
    spoken={'messages':[{'role':'system','content':'Full known identity. '+router.SPOKEN_MARKER+' y emotion.'}]}
    assert router.prepare(spoken)['messages'][0]['content'].startswith('Short identity.')


def test_windows_utf8_signature_does_not_prevent_matching_the_nas_identity(tmp_path,monkeypatch):
    monkeypatch.setattr(spoken_identity,'__file__',str(tmp_path/'spoken_identity.py'))
    (tmp_path/'identity-original.md').write_text('Full identity.',encoding='utf-8-sig')
    (tmp_path/'identity-voice.md').write_text('Short identity.',encoding='utf-8')
    assert spoken_identity.load_identities()==('Full identity.','Short identity.')


def test_identical_words_with_different_line_wrapping_still_match():
    messages=[{'role':'system','content':'Full\nknown identity.\nSaved memory.'}]
    assert compact_messages(messages,'Full\n\nknown identity.','Brief identity.')[0]['content']=='Brief identity.\nSaved memory.'
    changed=[{'role':'system','content':'Full changed identity.'}]
    assert compact_messages(changed,'Full known identity.','Brief identity.')==changed


def test_content_blocks_and_developer_role_preserve_memory_and_cache_metadata(monkeypatch):
    monkeypatch.setattr(router,'IDENTITIES',('Full identity.','Short identity.'))
    blocks=[{'type':'text','text':'Full identity.','cache_control':{'type':'ephemeral'}},
        {'type':'text','text':'Saved memory: blue. '+router.SPOKEN_MARKER}]
    body={'messages':[{'role':'developer','content':blocks},{'role':'user','content':'Hello'}]}
    assert router.spoken_request(body)
    compact=router.prepare(body)
    assert compact['messages'][0]['content'][0]=={'type':'text','text':'Short identity.','cache_control':{'type':'ephemeral'}}
    assert compact['messages'][0]['content'][1]==blocks[1]
    assert body['messages'][0]['content']==blocks
    assert 'response_format' in compact
    assert compact['cache_prompt'] is True
    assert not router.spoken_request({'messages':[{'role':'user','content':router.SPOKEN_MARKER}]})
