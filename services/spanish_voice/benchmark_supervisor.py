"""Pause only our isolated benchmark while Mochi is conversing."""
from pathlib import Path
import os
import json
import signal
import sqlite3
import subprocess
import sys
import time


def active():
    try:
        with sqlite3.connect('file:/shared/wake-models/jobs.sqlite3?mode=ro',uri=True,timeout=2) as db:
            return bool(db.execute('SELECT 1 FROM activity WHERE until>? LIMIT 1',(time.time(),)).fetchone())
    except sqlite3.Error:return True


while active():time.sleep(1)
pause_total=0.0
pause_file=Path('/results/pauses.json')
pause_file.write_text(json.dumps({'seconds':pause_total}))
mode=os.getenv('MOCHI_BENCH_MODE')
if mode not in ('hybrid','decoder'):raise ValueError('Use the approved voice build or decoder validation')
command=[sys.executable,'/app/decoder_trial.py'] if mode=='decoder' else ['sh','/app/cpp_trial.sh']
with Path('/results/benchmark.log').open('w') as output:
    child=subprocess.Popen(command,stdout=output,stderr=output,start_new_session=True)
    paused=False;pause_started=0
    while child.poll() is None:
        speaking=active()
        if speaking!=paused:
            if speaking:pause_started=time.monotonic()
            else:
                pause_total+=time.monotonic()-pause_started
                temporary=pause_file.with_suffix('.partial')
                temporary.write_text(json.dumps({'seconds':pause_total}));temporary.replace(pause_file)
            signal_to_send=signal.SIGSTOP if speaking else signal.SIGCONT
            try:os.killpg(child.pid,signal_to_send)
            except ProcessLookupError:break
            paused=speaking
        time.sleep(.25)
raise SystemExit(child.returncode)
