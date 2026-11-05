"""One leased CPU training job; foreground conversations suspend only our own child."""
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import time
import uuid

from wake_jobs import WakeJobs


def valid_model(path):
    """Apply the same artifact bounds to new and reused detector models."""
    try:
        if not 8<=path.stat().st_size<2097152:return False
        with path.open('rb') as source:return source.read(8)[4:]==b'TFL3'
    except OSError:return False


def main():
    root=Path(os.environ.get('MOCHI_WAKE_DIR','/shared/wake-models'))
    jobs=WakeJobs(root)
    worker=uuid.uuid4().hex
    while True:
        job=jobs.claim(worker)
        if job is None:
            time.sleep(2); continue
        directory=jobs.directory(job['id']); directory.mkdir(parents=True,exist_ok=True)
        reused=False
        with jobs.connect() as db:
            previous_jobs=db.execute("SELECT id,name FROM jobs WHERE stage='ready' ORDER BY updated DESC").fetchall()
        for identifier,name in previous_jobs:
            if name.casefold()!=job['name'].casefold(): continue
            previous=jobs.directory(identifier)
            try:
                report=json.loads((previous/'report.json').read_text())
                if (not isinstance(report,dict) or report.get('passed') is not True
                        or report.get('pipeline')!='mww-mochi-v10'
                        or not valid_model(previous/'model.tflite')): continue
                shutil.copy2(previous/'model.tflite',directory/'model.tflite')
                shutil.copy2(previous/'report.json',directory/'report.json')
            except (OSError,ValueError): continue
            jobs.update(job['id'],worker,'ready',100); reused=True; break
        if reused: continue
        # Reuse only this name's compatible, already separated train/validation
        # examples. Checkpoint weights and held-out evaluation remain distinct.
        if not (directory/'training.npz').exists():
            with jobs.connect() as db:
                cached=db.execute("SELECT id,name FROM jobs WHERE stage IN ('failed','ready') ORDER BY updated DESC LIMIT 32").fetchall()
            for identifier,name in cached:
                if name.casefold()!=job['name'].casefold(): continue
                previous=jobs.directory(identifier)
                try:
                    report=json.loads((previous/'report.json').read_text())
                    if not isinstance(report,dict) or report.get('pipeline')!='mww-mochi-v10': continue
                    shutil.copyfile(previous/'training.npz',directory/'training.npz')
                    break
                except (OSError,ValueError): continue
        with (directory/'training.log').open('ab',buffering=0) as log:
            child=subprocess.Popen([sys.executable,str(Path(__file__).with_name('train_name.py')),
                '--directory',str(directory),'--name',job['name'],
                '--voices',os.environ.get('MOCHI_TRAIN_VOICES','/shared/voices')],
                stdout=log,stderr=log,start_new_session=True)
            paused=False; active_seconds=0; previous=time.monotonic()
            try:
                while child.poll() is None:
                    now=time.monotonic()
                    if not paused: active_seconds+=now-previous
                    previous=now
                    active=jobs.conversation_active()
                    if active!=paused:
                        os.killpg(child.pid,signal.SIGSTOP if active else signal.SIGCONT)
                        paused=active
                    progress=directory/'progress.json'
                    stage,percent='preparing',0
                    if progress.is_file():
                        try:
                            data=json.loads(progress.read_text()); stage,percent=data['stage'],data['progress']
                        except (ValueError,KeyError,OSError): pass
                    jobs.update(job['id'],worker,stage,min(99,int(percent)))
                    if active_seconds>7200:
                        os.killpg(child.pid,signal.SIGKILL)
                        child.wait()
                        raise TimeoutError('training_timeout')
                    time.sleep(.5)
                report_path=directory/'report.json'
                report=json.loads(report_path.read_text()) if report_path.is_file() else {}
                model=directory/'model.tflite'
                valid=child.returncode==0 and isinstance(report,dict) and report.get('passed') is True and valid_model(model)
                failure='training_quality_not_met' if child.returncode==2 and report else 'training_unavailable'
                jobs.update(job['id'],worker,'ready' if valid else 'failed',100,None if valid else failure)
            except Exception:
                if child.poll() is None:
                    os.killpg(child.pid,signal.SIGKILL); child.wait()
                jobs.update(job['id'],worker,'failed',100,'training_unavailable')


if __name__=='__main__':
    main()
