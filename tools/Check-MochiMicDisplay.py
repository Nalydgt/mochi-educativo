"""Exercise microphone RX followed by NAS speech while measuring the real panel.

Microphone samples are overwritten on the board, never stored or transmitted.
"""
import argparse,json,re,time
from pathlib import Path
from mochi_device import Device
ROOT=Path(__file__).resolve().parents[1]
def fields(text):return {k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',text)}

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--port',default='COM3')
 p.add_argument('--rounds',type=int,default=3,choices=(1,2,3,4,5));a=p.parse_args()
 report={'passed':False,'microphone_samples_stored':False,'microphone_samples_transmitted':False,'rounds':[]}
 with Device(a.port) as d:
  report['firmware']=d.command('@firmware','@mochi_firmware ')
  before=fields(d.command('@controls','@mochi_controls '))['volume']
  d.port.write(b'@close\n');time.sleep(.2)
  try:
   for index in range(a.rounds):
    assert fields(d.command('@status','@mochi_status '))['busy']==0
    start=fields(d.command('@display','@mochi_display_ui '));d.reply('@mochi_display ')
    d.events.clear();d.port.write(b'@mic-speaker-test\n');deadline=time.monotonic()+80
    checks=0;misses=0;max_misses=0;completed=None
    while time.monotonic()<deadline:
     ui=fields(d.command('@display','@mochi_display_ui ',timeout=4))
     panel=fields(d.reply('@mochi_display ',timeout=4));checks+=1
     assert panel.get('serial_dma')==1 and panel['dma_restarts']==0,panel
     misses=misses+1 if not ui['lock'] else 0;max_misses=max(max_misses,misses)
     assert misses<3,'GUI stopped responding during microphone/speaker transition'
     completed=next((x for x in d.events if x.startswith('@mochi_mic_speaker ')),None)
     if completed:break
     time.sleep(.1)
    assert completed and 'result=ESP_OK' in completed,completed
    result=fields(completed)
    assert result['input_frames']>=48000 and result['played']==result['bytes']>0 and result['http']==200,completed
    assert ui['rendered']-start['rendered']>=10,'No real panel updates during the audio sequence'
    report['rounds'].append({'round':index+1,'completion':completed,'panel_checks':checks,
      'rendered_frames':ui['rendered']-start['rendered'],'max_consecutive_gui_lock_misses':max_misses,
      'dma_restarts':panel['dma_restarts']})
    print(json.dumps(report['rounds'][-1]),flush=True)
    time.sleep(.3)
   assert fields(d.command('@controls','@mochi_controls '))['volume']==before
   report.update(passed=True,volume_preserved=before)
  finally:
   (ROOT/'.runtime/mochi-mic-display-check.json').write_text(json.dumps(report,indent=2)+'\n')
 print('Microphone, NAS speech and panel progress: PASS',flush=True)

if __name__=='__main__':main()
