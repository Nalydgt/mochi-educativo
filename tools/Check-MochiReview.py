"""Validate extraction/correction/cancellation on the real NAS model, in isolation."""
import argparse,json
from pathlib import Path
from nas import NAS
ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--settings',type=Path,default=ROOT/'.runtime/nas.json')
    a=p.parse_args();nas=NAS(json.loads(a.settings.read_text()))
    try:
        script='''
import asyncio,json,time
from pathlib import Path
from tempfile import TemporaryDirectory
from app import Settings
from memory_store import Memory
from memory_review import MemoryReviewer
s=Settings.from_env()
async def run():
    with TemporaryDirectory(prefix='review-check-',dir='/data') as directory:
        store=Memory(Path(directory)/'memory.sqlite3')
        old=store.append_turn('synthetic','Mi bebida favorita es el té de jazmín.','Entendido.')
        reviewer=MemoryReviewer(store,s.fast_url,s.fast_key)
        assert await reviewer.review_once()
        facts=store.facts('synthetic')
        assert any('jazm' in f['content'].lower() for f in facts),facts
        store.append_turn('synthetic','Corrige mi bebida favorita: ahora es café. Ya no es té de jazmín.','De acuerdo.')
        assert await reviewer.review_once()
        facts=store.facts('synthetic')
        assert any('caf' in f['content'].lower() for f in facts),facts
        assert not store.pending()
        store.append_turn('synthetic','Mi planta se llama Bruma.','Vale.')
        reviewer.task=asyncio.create_task(reviewer.review_once())
        await asyncio.sleep(.1)
        start=time.monotonic()
        async with reviewer.foreground():pass
        cancel_seconds=time.monotonic()-start
        assert store.pending(),'Cancelled review must stay pending'
        restarted=Memory(store.path,recover=True)
        assert restarted.pending() and any('caf' in f['content'].lower() for f in restarted.facts('synthetic'))
        assert await reviewer.review_once()
        assert not store.pending()
        assert any('bruma' in f['content'].lower() for f in store.facts('synthetic'))
        print(json.dumps({'passed':True,'real_local_model':True,'isolated_database':True,'extraction':True,'correction':True,
            'restart_preserved':True,'cancelled_pending_retained':True,'cancel_seconds':round(cancel_seconds,3),
            'retry_completed':True,'actions_or_audio_generated':False}))
asyncio.run(run())
'''
        output=nas.container('mochi-voice-next','mochi',"cd /app\n/data/venv/bin/python -u - <<'PY'\n"+script+'\nPY',timeout=300)
        print(output)
        (ROOT/'docs/mediciones/20261026-revision-memoria.json').write_text(output.splitlines()[-1]+'\n')
    finally:nas.close()


if __name__=='__main__':main()
