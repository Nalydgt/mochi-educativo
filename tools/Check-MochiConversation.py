"""Observe a user-initiated real conversation; save numeric evidence only."""
import argparse,json,re,time
from pathlib import Path
from mochi_device import Device,voice_timings
ROOT=Path(__file__).resolve().parents[1]


def fields(text):return {k:int(v) for k,v in re.findall(r'(\w+)=(-?\d+)',text)}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--port',default='COM3')
    p.add_argument('--output',type=Path,default=ROOT/'.runtime/board-conversation-latency.json')
    p.add_argument('--timeout',type=int,default=240);a=p.parse_args()
    report={'passed':False,'user_started_conversation':True,'microphone_audio_stored_locally':False}
    with Device(a.port) as d:
        report['firmware']=d.command('@firmware','@mochi_firmware ')
        start=time.monotonic();active_samples=0;open_samples=0;ui_checks=0;last_check=0
        while time.monotonic()-start<a.timeout:
            line=d.command('@mochi-av','@mochi_av ',timeout=4);row=fields(line)
            if row.get('active') and row.get('speaking'):
                active_samples+=1
                if row.get('pose',0)>0:open_samples+=1
            if time.monotonic()-last_check>.5:
                d.command('@display','@mochi_display_ui ',timeout=4)
                panel=fields(d.reply('@mochi_display ',timeout=4))
                assert panel.get('dma_restarts')==0
                ui_checks+=1;last_check=time.monotonic()
            event=next((x for x in d.events if x.startswith('Voice response: ') and 'http=200' in x),None)
            if event:
                result=fields(event)
                assert result['bytes']>0 and result['played']==result['bytes'] and 'result=ESP_OK' in event,event
                assert active_samples>0 and open_samples>0,'No live I2S/mouth samples observed'
                report.update(passed=True,response=event,**voice_timings(result),
                    active_samples=active_samples,open_mouth_samples=open_samples,display_checks=ui_checks)
                break
            time.sleep(.08)
        else:raise TimeoutError('No complete user conversation observed')
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report),flush=True)


if __name__=='__main__':main()
