"""Compact the exact known persona for speech; retain Hermes' memory and rules."""
from pathlib import Path
import re


def instruction_texts(message):
    if message.get('role') not in ('system','developer'):return []
    content=message.get('content')
    if isinstance(content,str):return [content]
    if isinstance(content,list):
        return [part['text'] for part in content if isinstance(part,dict) and
            part.get('type')=='text' and isinstance(part.get('text'),str)]
    return []


def compact_messages(messages,full_identity,spoken_identity):
    if not full_identity.strip() or not spoken_identity.strip():return messages
    # Hermes and Windows editors may wrap the same identity differently.
    # Require every known word and punctuation mark, permitting whitespace
    # changes only. Any change of meaning keeps the full identity intact.
    pattern=re.compile(r'\s+'.join(re.escape(word) for word in full_identity.split()))
    def compact(text):return pattern.sub(lambda _:spoken_identity,text,count=1)
    result=[]
    for message in messages:
        content=message.get('content')
        if message.get('role') in ('system','developer'):
            if isinstance(content,str):message={**message,'content':compact(content)}
            elif isinstance(content,list):
                message={**message,'content':[{**part,'text':compact(part['text'])}
                    if isinstance(part,dict) and part.get('type')=='text' and isinstance(part.get('text'),str)
                    else part for part in content]}
        result.append(message)
    return result


def load_identities():
    root=Path(__file__).parent
    try:return ((root/'identity-original.md').read_text(encoding='utf-8-sig').strip(),
                (root/'identity-voice.md').read_text(encoding='utf-8-sig').strip())
    except OSError:return ('','')
