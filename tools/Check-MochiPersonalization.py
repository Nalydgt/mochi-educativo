"""Exercise the live wardrobe with LVGL pointer events; preserve the user's look."""
import argparse,json,re,struct,subprocess,sys,time,zlib
from pathlib import Path
from mochi_device import Device

ROOT=Path(__file__).resolve().parents[1]
FIELDS=('outfit','color','expression','motion')
COUNTS=(12,6,8,3)
def fields(text):return {k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',text)}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',default='COM3')
    args=parser.parse_args()
    target=ROOT/'.runtime/personalization-previews';target.mkdir(exist_ok=True)
    report={'passed':False,'physical_touch_tested':False,'input':'LVGL pointer events',
            'tab_checks':0,'swipe_checks':0,'button_checks':0}
    def pointer(device,x,y,pressed):
        assert device.command(f'@ui-pointer {x} {y} {int(pressed)}','@mochi_ui_pointer ').endswith('ok')
        time.sleep(.055)
    def click(device,x,y):
        pointer(device,x,y,True);pointer(device,x,y,False);time.sleep(.1)
    def swipe(device,direction):
        start,end=(295,175) if direction>0 else (175,295)
        for i in range(7):pointer(device,round(start+(end-start)*i/6),205,True)
        pointer(device,end,205,False);time.sleep(.15)
    def capture(name):
        subprocess.run([sys.executable,str(ROOT/'tools/Capture-Mochi.py'),str(target/name),
                        '--port',args.port,'--current','--delay','.3'],check=True,capture_output=True)
        data=(target/name).read_bytes();offset=8;compressed=bytearray()
        while offset<len(data):
            size=struct.unpack_from('>I',data,offset)[0];kind=data[offset+4:offset+8]
            if kind==b'IDAT':compressed.extend(data[offset+8:offset+8+size])
            offset+=size+12
        rows=zlib.decompress(compressed);stride=466*3+1
        assert all(rows[y*stride]==0 for y in range(466))
        visible=sum(max(rows[y*stride+1+x*3:y*stride+4+x*3])>50
                    for y in range(105,264) for x in range(128,338))
        assert visible>3000,('Mochi disappeared from live preview',name,visible)

    with Device(args.port) as device:
        original=fields(device.command('@appearance','@appearance '))
        report['firmware']=device.command('@firmware','@mochi_firmware ')
        device.port.write(b'@dashboard 9\n');time.sleep(.3)
    try:
        with Device(args.port) as device:
            ui=fields(device.command('@personalize','@mochi_personalize '))
            assert ui['active'] and ui['preview'] and ui['fonts_missing']==0,ui
            report['fonts_missing']=ui['fonts_missing']
            for field,count in enumerate(COUNTS):
                click(device,113+80*field,320)
                ui=fields(device.command('@personalize','@mochi_personalize '))
                assert ui['field']==field,ui
                report['tab_checks']+=1
                before=fields(device.command('@appearance','@appearance '))
                for direction in (1,-1):
                    swipe(device,direction)
                    after=fields(device.command('@appearance','@appearance '))
                    assert after[FIELDS[field]]==(before[FIELDS[field]]+direction)%count,(field,direction,before,after)
                    assert all(after[k]==before[k] for k in FIELDS if k!=FIELDS[field])
                    before=after;report['swipe_checks']+=1
                click(device,353,369)
                after=fields(device.command('@appearance','@appearance '))
                assert after[FIELDS[field]]==(before[FIELDS[field]]+1)%count
                report['button_checks']+=1
            # A long caption, accented expression and a large costume in the
            # same preview expose clipping, missing glyphs and memory pressure.
            device.command('@appearance-set 0 8','@appearance_set ')
            device.command('@appearance-set 1 3','@appearance_set ')
            device.command('@appearance-set 2 2','@appearance_set ')
            click(device,273,320)
        capture('expression.png')
        with Device(args.port) as device:
            click(device,113,320)
        capture('wardrobe.png')
        with Device(args.port) as device:
            click(device,193,320)
        capture('colour.png')
        with Device(args.port) as device:
            click(device,233,436)
            assert not fields(device.command('@personalize','@mochi_personalize '))['active']
            report['done_returns_to_mochi']=True
            for _ in range(4):
                device.port.write(b'@dashboard 9\n');time.sleep(.15)
                click(device,106,71)
                assert not fields(device.command('@personalize','@mochi_personalize '))['active']
                device.port.write(b'@close\n');time.sleep(.1)
            report['reopen_checks']=4
    finally:
        with Device(args.port) as device:
            device.command('@ui-pointer -1 -1 0','@mochi_ui_pointer ')
            for field,key in enumerate(FIELDS):device.command(f'@appearance-set {field} {original[key]}','@appearance_set ')
            device.port.write(b'@close\n@emote idle\n');time.sleep(1)
            after=fields(device.command('@appearance','@appearance '))
            assert all(after[k]==original[k] for k in FIELDS) and after['saved']
            report['appearance_preserved']=True
    report['passed']=True
    (ROOT/'.runtime/mochi-personalization-ui-check.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report),flush=True)

if __name__=='__main__':main()
