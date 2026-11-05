"""Verify the real private VPN and authenticated NAS request across restarts.

No credentials are read or changed. The display's status alone cannot pass.
"""
import argparse,json,re,time
from pathlib import Path
from mochi_device import Device

ROOT=Path(__file__).resolve().parents[1]
def numbers(text):return {k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',text)}
def appearance(device):
    p=numbers(device.command('@appearance','@appearance '))
    return {k:p[k] for k in ('outfit','color','expression','motion')}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',default='COM3')
    parser.add_argument('--rounds',type=int,choices=(1,2,3,4),default=3)
    parser.add_argument('--output',type=Path,default=ROOT/'.runtime/mochi-vpn-reboot-check.json')
    args=parser.parse_args()
    report={'passed':False,'rounds':[],'fresh_microphone_audio':False}
    with Device(args.port) as device:
        before=appearance(device);volume=numbers(device.command('@controls','@mochi_controls '))['volume']
        report['firmware']=device.command('@firmware','@mochi_firmware ')
    try:
        first_ip=None
        for round_index in range(args.rounds):
            if round_index:
                with Device(args.port) as device:
                    idle_until=time.monotonic()+120
                    while numbers(device.command('@status','@mochi_status '))['busy']:
                        if time.monotonic()>idle_until:raise TimeoutError('Active conversation did not finish before reboot check')
                        time.sleep(2)
                    assert device.command('@restart','@mochi_restart ')=='@mochi_restart queued'
                time.sleep(2)
            start=time.monotonic();deadline=start+100;last=None
            while time.monotonic()<deadline:
                try:
                    with Device(args.port) as device:
                        reply=device.command('@vpn','@mochi_vpn ',timeout=4);vpn=numbers(reply)
                        if vpn['phase']==4:raise RuntimeError('VPN startup failed: '+reply)
                        if vpn['ready']:
                            if numbers(device.command('@status','@mochi_status '))['busy']:
                                raise TimeoutError('Conversation owns the server connection')
                            assert vpn['crypto']==1 and vpn['persistent']==1 and vpn['relay']==1,reply
                            assert vpn['error']==0,reply
                            ip=re.search(r'\bip=([\d.]+)',reply)[1]
                            if first_ip is None:first_ip=ip
                            assert ip==first_ip,'VPN identity changed after restart'
                            server=device.command('@server','@mochi_server ',timeout=30)
                            if 'busy=1' in server:raise TimeoutError('Conversation started during server check')
                            assert 'http=200 ready=1' in server,server
                            firmware=device.command('@firmware','@mochi_firmware ')
                            assert report['firmware'].split()[1] in firmware and 'state=2' in firmware,firmware
                            ui=numbers(device.command('@display','@mochi_display_ui '))
                            panel=numbers(device.reply('@mochi_display '))
                            if not ui['lock']:
                                time.sleep(.1)
                                ui=numbers(device.command('@display','@mochi_display_ui '))
                                panel=numbers(device.reply('@mochi_display '))
                            assert ui['lock']==1 and panel.get('dma_restarts')==0,(ui,panel)
                            assert appearance(device)==before
                            assert numbers(device.command('@controls','@mochi_controls '))['volume']==volume
                            report['rounds'].append({'round':round_index+1,'restarted':bool(round_index),
                                'seconds':round(time.monotonic()-start,3),'vpn':reply,'server':server,'firmware':firmware,
                                'display':panel,'ui':ui})
                            print(json.dumps({'round':round_index+1,'connected':True,'nas_http':200,
                                'internal_free':vpn['internal_free'],'internal_largest':vpn.get('internal_largest')}),flush=True)
                            break
                except (OSError,TimeoutError) as error:last=error
                time.sleep(2)
            else:raise TimeoutError('VPN did not become usable after restart') from last
        report.update(passed=True,appearance_preserved=True,volume_preserved=volume,
                      identity_preserved=True,software_restarts=args.rounds-1)
    finally:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('VPN startup and authenticated NAS access: PASS',flush=True)

if __name__=='__main__':main()
