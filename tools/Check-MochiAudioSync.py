"""Measure the real I2S output against Mochi's live mouth, then play NAS speech.

The pulse probe includes real silence, so an unrelated looping talking GIF
cannot pass. No microphone audio is recorded or sent.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import time

ROOT=Path(__file__).resolve().parents[1]


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


installer=module('mochi_installer',ROOT/'tools/mochi_device.py')


def probe(device,command,marker,output):
    device.events.clear();device.port.write((command+'\n').encode())
    start=time.monotonic();last=None;stable_since=start
    rows=[];checked=[];closed=open_mouth=0;end_event=None
    while time.monotonic()-start<120:
        line=device.command('@mochi-av','@mochi_av ')
        row={key:int(value) for key,value in re.findall(r'([a-z_]+)=(\d+)',line)}
        if row.get('tap')!=1:raise RuntimeError('Real I2S output monitor is unavailable')
        now=time.monotonic();row['elapsed_ms']=round((now-start)*1000)
        rows.append(row)
        # A phoneme can change during the 16 ms between UI updates. The native
        # firmware exposes the exact completed DMA sample used by that frame.
        # Keep the independent sustained tone/silence assertion, and compare
        # speech against its matching sample instead of a later phoneme.
        coherent=command!='@av-test' and 'mouth_level' in row
        expected=row['mouth_level' if coherent else 'level']>=30
        phase=(expected,row['active'],row['speaking'])
        if phase!=last:stable_since=now;last=phase
        if row['active'] and row['speaking'] and now-stable_since>=.12:
            checked.append(row)
            if expected:
                if row['pose']==0:
                    (output/'closed-during-audio.json').write_text(json.dumps(rows,indent=2))
                    raise RuntimeError('Mouth stayed closed during sustained DAC audio: '+str(row))
                open_mouth+=1
            else:
                if row['pose']!=0:raise RuntimeError('Mouth kept talking during actual DAC silence')
                closed+=1
            if coherent and not 0<=row['sequence']-row['mouth_sequence']<=5:
                raise RuntimeError('The mouth did not follow the completed DMA sequence: '+str(row))
            if row['ui_age_ms']>100 or row['sample_age_ms']+row['ui_age_ms']>80:
                (output/'stale-output.json').write_text(json.dumps(rows,indent=2))
                raise RuntimeError('The live mouth is using stale audio output: '+str(row))
        end_event=next((event for event in device.events if event.startswith(marker)),None)
        if end_event:break
        time.sleep(.02)
    if not end_event or 'result=ESP_OK' not in end_event:raise RuntimeError(str(end_event))
    time.sleep(.15)
    final=device.command('@mochi-av','@mochi_av ')
    end={key:int(value) for key,value in re.findall(r'([a-z_]+)=(\d+)',final)}
    if end['active'] or end['pose'] or end['speaking']:raise RuntimeError('The face did not stop with the speaker')
    active=[r for r in rows if r['active'] and r['speaking']]
    if not active or max(r['level'] for r in active)<110:raise RuntimeError('No actual output was observed')
    if command=='@av-test' and (closed<8 or open_mouth<8):
        raise RuntimeError(f'Not enough stable tone/silence samples: {open_mouth}/{closed}')
    return {'command':command,'completion':end_event,'samples':len(rows),
            'stable_open_samples':open_mouth,'stable_closed_samples':closed,
            'max_audio_sample_age_ms':max((r['sample_age_ms'] for r in checked),default=0),
            'max_effective_sample_age_ms':max((r['sample_age_ms']+r['ui_age_ms'] for r in checked),default=0),
            'max_ui_age_ms':max((r['ui_age_ms'] for r in checked),default=0),
            'poses_observed':sorted({r['pose'] for r in active}),
            'stopped_with_audio':True,'timeline':rows}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',default='COM3')
    parser.add_argument('--output',type=Path,default=ROOT/'.runtime/mochi-audio-sync')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    report={'passed':False,'source':'actual completed I2S DMA buffers','microphone_tested':False}
    with installer.Device(args.port) as device:
        report['firmware']=device.command('@firmware','@mochi_firmware ')
        device.port.write(b'@close\n');time.sleep(.2)
        before=device.command('@controls','@mochi_controls ')
        volume=re.search(r'volume=(\d+) saved=(\d+)',before).groups()
        try:
            report['pulse']=probe(device,'@av-test','@mochi_av_test ',args.output)
            print('Actual DAC tone/silence synchronization: PASS',flush=True)
            # Bulk snapshots are intentionally disabled while voice is busy.
            # Keep the speech measurement uninterrupted and use live UI state.
            report['nas_speech']=probe(device,'@speaker-stream-test','@mochi_speaker_stream ',args.output)
            print('NAS speech animation and stop: PASS',flush=True)
            after=device.command('@controls','@mochi_controls ')
            if re.search(r'volume=(\d+) saved=(\d+)',after).groups()!=volume:
                raise RuntimeError('Volume preference changed')
            report['volume_preserved']=int(volume[0]);report['passed']=True
        finally:
            device.port.write(b'@close\n@emote idle\n')
            (args.output/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'volume':report['volume_preserved'],
        'stable_silent_samples':report['pulse']['stable_closed_samples'],
        'stable_audible_samples':report['pulse']['stable_open_samples'],
        'nas_poses':report['nas_speech']['poses_observed']}),flush=True)


if __name__=='__main__':main()
