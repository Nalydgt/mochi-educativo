"""Exercise the native Coucou catalogue and output timing on the real board.

Preserves the user's appearance and volume. No microphone audio is recorded.
"""
import argparse
import json
from pathlib import Path
import re
import time
from mochi_device import Device

ROOT=Path(__file__).resolve().parents[1]
FIELDS=('outfit','color','expression','motion')

def numbers(line):
    return {key:int(value) for key,value in re.findall(r'([a-z_]+)=(\d+)',line)}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',default='COM3')
    parser.add_argument('--output',type=Path,default=ROOT/'.runtime/mochi-animation-check.json')
    args=parser.parse_args()
    catalogue=json.loads((ROOT/'firmware/assets/mochi/native-catalog.json').read_text(encoding='utf-8'))
    report={'passed':False,'renderer':'native','count':len(catalogue['animations']),
            'physical_touch_tested':False,'timing':{}}
    with Device(args.port) as device:
        device.port.write(b'@close\n');time.sleep(.2)
        identity=device.command('@animation','@animation ')
        assert 'character=Mochi hardware=1.75-G renderer=native loaded=1' in identity,identity
        report['firmware']=device.command('@firmware','@mochi_firmware ')
        report['initial_status']=identity
        appearance=numbers(device.command('@appearance','@appearance '))
        before=numbers(device.command('@controls','@mochi_controls '))
        try:
            for round_number in range(2):
                for asset in catalogue['animations']:
                    reply=device.command('@animation-play '+asset['id'],'@animation_play ')
                    assert reply=='@animation_play ok',(asset['id'],reply)
                    time.sleep(.055)
                    status=device.command('@animation','@animation ')
                    assert 'loaded=1 animation='+asset['id']+' ' in status,status
                print('All native animations played; round',round_number+1,flush=True)
            report['animation_swaps']=len(catalogue['animations'])*2
            assert device.command('@animation-play missing','@animation_play ').endswith('unavailable')
            # Measure named scenarios with a known look, then restore the user's
            # choice. A separate clothed dance catches costume transform cost.
            for field in range(4):device.command(f'@appearance-set {field} 0','@appearance_set ')
            cases=[(c,c,0) for c in ('working','dance','outfit_witchHat','outfit_pumpkin','mini_love','mailbox')]
            cases.append(('dance_beanie','dance',2))
            for case,clip,outfit in cases:
                device.command(f'@appearance-set 0 {outfit}','@appearance_set ')
                device.command('@animation-play '+clip,'@animation_play ')
                start=numbers(device.command('@animation','@animation '))
                screen_start=numbers(device.command('@display','@mochi_display_ui '))
                started=time.monotonic()
                time.sleep(2.5)
                end=numbers(device.command('@animation','@animation '))
                screen_end=numbers(device.command('@display','@mochi_display_ui '))
                elapsed=time.monotonic()-started
                fps=(end['frame']-start['frame'])/elapsed
                result={'frames':end['frame']-start['frame'],'seconds':round(elapsed,3),
                        'updates_per_second':round(fps,2),'mean_interval_ms':end['mean_us']/1000,
                        'max_interval_ms':end['max_us']/1000,'last_model_render_ms':end.get('render_us',0)/1000,
                        'rendered_frames_per_second':round((screen_end['rendered']-screen_start['rendered'])/elapsed,2)}
                if 'body_frames' in end:
                    result['body_poses_per_second']=round((end['body_frames']-start['body_frames'])/elapsed,2)
                result['outfit']=outfit if not clip.startswith('outfit_') else (8 if clip=='outfit_witchHat' else 9)
                report['timing'][case]=result
                print(case,json.dumps(result),flush=True)
            device.command('@animation-play greet','@animation_play ')
            time.sleep(3)
            assert 'animation=idle ' in device.command('@animation','@animation ')
            for command,prefix in (('@audio-test','@mochi_audio_test '),('@voice-policy-test','@mochi_voice_policy_test '),
                                   ('@voice-errors-test','@mochi_voice_errors_test '),('@vpn-test','@mochi_vpn_test ')):
                reply=device.command(command,prefix)
                assert reply.endswith('PASS'),reply
            report['self_tests']=4
            reply=device.command('@server','@mochi_server ',timeout=35)
            assert 'http=200 ready=1' in reply,reply
            report['nas_over_vpn']=True
            after=numbers(device.command('@controls','@mochi_controls '))
            assert (after['volume'],after['saved'])==(before['volume'],before['saved'])
            report['volume_preserved']=before['volume']
            assert all(r['updates_per_second']>=20 and r['rendered_frames_per_second']>=20 and r['max_interval_ms']<=100
                       for r in report['timing'].values()),report['timing']
            assert report['timing']['dance'].get('body_poses_per_second',0)>=20,report['timing']['dance']
            report['passed']=True
        finally:
            for field,key in enumerate(FIELDS):
                assert device.command(f'@appearance-set {field} {appearance[key]}','@appearance_set ').endswith('ok')
            device.port.write(b'@close\n@emote idle\n')
            report['appearance_preserved']={key:appearance[key] for key in FIELDS}
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report),flush=True)

if __name__=='__main__':main()
