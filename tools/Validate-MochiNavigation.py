"""Exercise both travel modes on the real board using labelled synthetic GPS.

Uses public Berlin landmarks, native touch events, NAS routes and cached voice.
Never writes the LC76G/NVS position. Restores real GPS and ends the demo in a
finally block. Outdoor travel remains a separate human acceptance check.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.request import Request, urlopen
import uuid

from mochi_device import Device, voice_timings
from nas import NAS

ROOT = Path(__file__).resolve().parents[1]


def playback_diagnostic(device, played_bytes):
    """Retry one lost USB diagnostic reply without replaying the audio cue."""
    for retries in range(2):
        try:
            playback = device.command('@audio', '@mochi_playback', timeout=3)
        except TimeoutError:
            if retries:
                raise
            continue
        timing = re.search(r'pcm_ms=(\d+) wall_ms=(\d+)', playback)
        if not timing:
            raise RuntimeError('Invalid playback diagnostic')
        pcm_ms, wall_ms = map(int, timing.groups())
        if abs(pcm_ms-played_bytes*1000/32000) > 1:
            raise RuntimeError('Playback diagnostic does not match the completed cue')
        if abs(wall_ms-pcm_ms) >= 500:
            raise RuntimeError('Playback duration differs from its PCM duration')
        return {'pcm_ms': pcm_ms, 'wall_ms': wall_ms, 'diagnostic_retries': retries}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--settings', type=Path, default=ROOT/'.runtime/nas.json')
    parser.add_argument('--port', default='COM3')
    parser.add_argument('--output', type=Path, default=ROOT/'.runtime/navigation-hardware')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    settings = json.loads(args.settings.read_text(encoding='utf-8'))
    headers = {'Authorization':'Bearer '+Path(settings['device_key_file']).read_text().strip(),
               'X-Device-ID':settings['device']}
    base = 'http://'+settings['host']+':8765'
    report = {'synthetic_gps': True, 'physical_outdoor_trip': False, 'modes': [], 'captures': []}
    session = None

    def api(route, body=None):
        request = Request(base+route, data=json.dumps(body).encode() if body is not None else None,
                          headers={**headers, 'Content-Type':'application/json'})
        with urlopen(request, timeout=40) as response: return json.load(response)

    def command(text, prefix):
        with Device(args.port) as device: return device.command(text, prefix, timeout=12)

    def click(x, y, hold=.18):
        with Device(args.port) as device:
            assert 'ok' in device.command(f'@ui-pointer {x} {y} 1', '@mochi_ui_pointer')
            time.sleep(hold)
            assert 'ok' in device.command(f'@ui-pointer {x} {y} 0', '@mochi_ui_pointer')
        time.sleep(.4)

    def wait(test, timeout=90):
        deadline = time.monotonic()+timeout
        while time.monotonic() < deadline:
            state = api('/v1/navigation/active')
            if test(state): return state
            time.sleep(1)
        raise TimeoutError('Navigation did not reach the expected state')

    def capture(name):
        # Firmware deliberately ignores bulk snapshots while audio owns its
        # reply buffer. A map may become ready before its spoken cue finishes.
        started = time.monotonic()
        deadline = started + 45
        with Device(args.port) as device:
            while time.monotonic() < deadline:
                status = device.command('@status', '@mochi_status')
                if re.search(r'\bbusy=0\b', status):
                    time.sleep(.25)
                    if re.search(r'\bbusy=0\b', device.command('@status', '@mochi_status')):
                        break
                time.sleep(.2)
            else:
                raise TimeoutError('Audio did not release the frame buffer before capture')
        subprocess.run([sys.executable, str(ROOT/'tools/Capture-Mochi.py'),
                        str(args.output/(name+'.png')), '--port', args.port, '--current'], check=True)
        report['captures'].append({'name': name, 'idle_wait_seconds': round(time.monotonic()-started, 3)})

    def wait_ui(phase, timeout=75):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            diagnostic=command('@navigation','@mochi_navigation')
            if 'phase='+phase+' ' in diagnostic: return diagnostic
            time.sleep(1)
        raise TimeoutError('Board UI did not reach '+phase)

    def remote(source):
        nas = NAS(settings)
        try: return nas.container('mochi-voice','mochi', "cd /app\n/data/gateway-runtime/venv/bin/python - <<'PY'\n"+source+'\nPY')
        finally: nas.close()

    def position(point):
        assert 'ok' in command('@navigation-simulation %.7f %.7f'%(point[1],point[0]), '@mochi_navigation_simulation')

    try:
        for mode, x in [('foot',152),('car',314)]:
            position([13.38886,52.517037])
            session = remote("from navigation import Navigation\nn=Navigation('/data')\nprint(n.start("+
                             repr(settings['device'])+",'Brandenburger Tor Berlin',"+repr('navigation-demo-'+uuid.uuid4().hex)+"))").strip()
            assert re.fullmatch('[a-f0-9]{32}',session)
            with Device(args.port) as device:
                device.port.write(('@navigation-session '+session+'\n').encode())
            wait(lambda s:s['id']==session and s['phase']=='choose_mode')
            wait_ui('choose_mode')
            capture(mode+'-choice')
            click(x,222)
            state = wait(lambda s:s['phase'] in {'choose_destination','guiding','unavailable'})
            if state['phase']=='choose_destination':
                wait_ui('choose_destination'); click(230,182)
            state = wait(lambda s:s['phase']=='guiding')
            deadline = time.monotonic()+60
            while time.monotonic()<deadline:
                diagnostic=command('@navigation','@mochi_navigation')
                if re.search(r'map=[0-9]+',diagnostic): break
                time.sleep(1)
            else: raise TimeoutError('No rendered map on the board')
            capture(mode+'-map')
            item={'mode':mode,'map_on_board':True,'gps_pause':False,'audio':[]}
            report['modes'].append(item)
            if mode=='foot':
                route=json.loads(remote("import json\nfrom navigation import Navigation\ns=Navigation('/data').load("+repr(settings['device'])+","+repr(session)+")\nassert s['query']=='Brandenburger Tor Berlin'\nprint(json.dumps(s['route']))"))
                step=next(step for step in route['steps'][1:] if step['at']>30 and step['cue']!='arrive')
                def point_at(metres):
                    c=route['cumulative'];g=route['geometry']
                    i=next(i for i in range(len(c)-1) if c[i+1]>=metres)
                    f=(metres-c[i])/(c[i+1]-c[i])
                    return [g[i][j]+f*(g[i+1][j]-g[i][j]) for j in range(2)]
                for metres in (max(1,step['at']-30),step['at']-8):
                    with Device(args.port) as device:
                        p=point_at(metres)
                        device.command('@navigation-simulation %.7f %.7f'%(p[1],p[0]),'@mochi_navigation_simulation')
                        audio=device.reply('Voice response:',timeout=40)
                        assert 'result=ESP_OK' in audio and 'http=200' in audio
                        match=re.search(r'bytes=(\d+).*played=(\d+).*first_audio_ms=(\d+)',audio)
                        assert match and match[1]==match[2]
                        time.sleep(.3)
                        timing=playback_diagnostic(device,int(match[2]))
                        audio_fields={k:int(v) for k,v in re.findall(r'(\w+)=(-?\d+)',audio)}
                        item['audio'].append({'bytes':int(match[1]),'played_bytes':int(match[2]),
                            **voice_timings(audio_fields),**timing})
            command('@navigation-simulation lost','@mochi_navigation_simulation')
            wait(lambda s:s['phase']=='gps_waiting')
            wait_ui('gps_waiting');capture(mode+'-gps-paused');item['gps_pause']=True
            position([13.38886,52.517037])
            wait(lambda s:s['phase']=='guiding')
            click(165,420)
            assert 'visible=0' in command('@navigation','@mochi_navigation')
            click(233,405)
            assert 'visible=1' in command('@navigation','@mochi_navigation')
            item['return_to_mochi_and_map']=True
            click(293,420)
            wait(lambda s:s['phase']=='cancelled')
            item['cancelled_by_touch']=True
        report['firmware']=command('@firmware','@mochi_firmware')
        report['navigation_self_test']=command('@navigation-test','@mochi_navigation_test')
        report['display_self_test']=command('@display-test','@mochi_display_test')
        report['vpn_self_test']=command('@vpn-test','@mochi_vpn_test')
        report['passed']=True
    finally:
        if session:
            try: api('/v1/navigation/'+session,{'action':'cancel'})
            except Exception: pass
        try:
            command('@navigation-simulation off','@mochi_navigation_simulation')
            command('@ui-pointer -1 -1 0','@mochi_ui_pointer')
        finally: (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
