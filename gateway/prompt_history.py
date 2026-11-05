"""Bounded, volatile replay of exact model messages; durable history stays plain.

Replacing last turn's JSON with plain text invalidates the model prefix.
Rolling the window every turn also shifts its attention cache. Retain exact
messages in RAM and compact in batches while the successful tail matches
SQLite. Runtime facts and weather coordinates never enter durable history.
"""
from collections import OrderedDict
import json


class PromptHistory:
    def __init__(self,max_devices=8):
        self.entries=OrderedDict();self.max_devices=max_devices

    def for_turn(self,device,stored):
        entry=self.entries.get(device)
        if entry and entry[0]==stored:
            self.entries.move_to_end(device)
            return [dict(m) for m in entry[1]]
        self.entries.pop(device,None)
        return [dict(m) for m in stored]

    def for_fast_turn(self,device,stored,current,max_characters=10000):
        """Append exact prompts until their runtime context needs compaction.

        Keep the current recall intact. Older envelopes can contain kilobytes
        of obsolete recall/device facts, so compact them in batches to recent
        durable question/answer pairs rather than shifting the cache each turn.
        """
        entry=self.entries.get(device)
        committed=entry is not None and entry[0]==stored
        replay=self.for_turn(device,stored) if committed else [dict(m) for m in stored[-12:]]
        if not committed:self.entries.pop(device,None)
        size=len(current['content'])+sum(len(m['content']) for m in replay)
        if size>max_characters:
            replay=[dict(m) for m in stored[-12:]]
            size=len(current['content'])+sum(len(m['content']) for m in replay)
            while replay and size>max_characters:
                # Delivered history consists of complete question/answer pairs.
                # Never truncate a word, fabricate a summary or drop new recall.
                size-=sum(len(m['content']) for m in replay[:2])
                del replay[:2]
        return replay+[dict(current)]

    def propose(self,device,stored,messages,question,answer):
        expected=(stored+[{'role':'user','content':question},
            {'role':'assistant','content':answer['text']}])[-24:]
        raw=getattr(answer,'model_content',None)
        if raw is None:raw=json.dumps(answer,ensure_ascii=False,separators=(',',':'))
        replay=messages+[{'role':'assistant','content':raw}]
        # Keep the native cache append-only between bounded compactions. A
        # rolling 24-message window forces a costly attention shift on every
        # question even when the model reports most tokens as cached.
        if len(replay)>48:replay=replay[-24:]
        # This proposal becomes usable only after the successful turn commits.
        # Disconnects, failed audio or externally changed history fail the match.
        self.entries[device]=(expected,[dict(m) for m in replay])
        self.entries.move_to_end(device)
        while len(self.entries)>self.max_devices:self.entries.popitem(last=False)
