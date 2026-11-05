"""Synthetic streets/positions only. No household GPS data in fixtures."""
import struct

import httpx
import pytest
from PIL import Image
from fastapi.testclient import TestClient

from app import Settings, create_app
from navigation import Navigation, Providers, Unavailable, CUES, intent, WIDTH, HEIGHT, distance
from test_gateway import Brain, Speech, TOKEN, HEADERS

ORIGIN = [13.38886, 52.517037]
END = [13.38886, 52.519037]
LOCATION = {'latitude': ORIGIN[1], 'longitude': ORIGIN[0], 'current': True, 'age_seconds': 0}


class FakeProviders:
    def __init__(self, candidates=1):
        self.calls = []
        self.candidates = candidates
        self.fail = False

    def search(self, query, position):
        self.calls.append(('search', query))
        return [{'label': f'Destino {i+1}', 'point': END} for i in range(self.candidates)]

    def route(self, origin, destination, mode):
        self.calls.append(('route', mode))
        if self.fail: raise Unavailable()
        points = [origin, [origin[0], origin[1]+.001], destination]
        cumulative = [0, distance(points[0], points[1]), 0]
        cumulative[-1] = cumulative[1]+distance(points[1], points[2])
        return {'geometry': points, 'cumulative': cumulative, 'length': cumulative[-1], 'duration': 180,
                'steps': [{'at': 0, 'cue': 'straight', 'instruction': 'Inicia la marcha'},
                          {'at': cumulative[1], 'cue': 'right', 'instruction': 'Gira a la derecha · Calle de prueba'},
                          {'at': cumulative[-1], 'cue': 'arrive', 'instruction': 'Llegada'}]}

    def tile(self, z, x, y): return Image.new('RGB', (256, 256), '#e5e7eb')


def fixture(tmp_path, count=1):
    now = [1_000_000.]
    provider = FakeProviders(count)
    nav = Navigation(tmp_path, provider, lambda: now[0])
    identifier = nav.start('board', 'Museo de prueba', 'exchange-1', LOCATION)
    return nav, provider, now, identifier


@pytest.mark.parametrize('text', ['¿Cómo ir a la estación?', 'Cómo llegar al museo', 'Llévame a la plaza',
                                 'Guíame hasta el parque', 'Quiero ir a Madrid', 'Inicia una ruta a Toledo'])
def test_spanish_navigation_intent(text):
    assert intent(text)[0] == 'start'


@pytest.mark.parametrize('text', ['¿Cómo funciona el GPS?', 'Quiero saber cómo ir vestido',
                                 '¿Cómo llegar a ser médico?', 'Guarda que vivo en Madrid'])
def test_knowledge_and_memories_are_not_navigation(text):
    assert intent(text) is None


def test_mode_choice_gps_freshness_and_restart(tmp_path):
    nav, provider, now, identifier = fixture(tmp_path)
    assert nav.status('board')['phase'] == 'choose_mode'
    assert provider.calls == []
    for stale in (None, {**LOCATION, 'current': False}, {**LOCATION, 'age_seconds': 11}):
        result = nav.update('board', identifier, action='mode', mode='foot', location=stale)
        assert result['phase'] == 'gps_waiting'
        assert provider.calls == []
    assert nav.update('board', identifier, location=LOCATION)['phase'] == 'guiding'
    assert provider.calls[-1] == ('route', 'foot')
    assert Navigation(tmp_path, provider, lambda: now[0]).status('board')['phase'] == 'guiding'
    now[0] += 11
    assert Navigation(tmp_path, provider, lambda: now[0]).status('board')['phase'] == 'gps_waiting'
    assert nav.status('board')['cue'] == ''


def test_destination_selection_idempotence_and_device_scope(tmp_path):
    nav, provider, _, identifier = fixture(tmp_path, 3)
    assert nav.start('board', 'Museo de prueba', 'exchange-1', LOCATION) == identifier
    result = nav.update('board', identifier, action='mode', mode='car', location=LOCATION)
    assert result['phase'] == 'choose_destination'
    assert len(result['candidates']) == 3
    assert all(call[0] != 'route' for call in provider.calls)
    with pytest.raises(KeyError): nav.update('other-board', identifier)
    with pytest.raises(ValueError): nav.update('board', identifier, action='destination', candidate=3, location=LOCATION)
    assert nav.update('board', identifier, action='destination', candidate=1, location=LOCATION)['phase'] == 'guiding'
    assert nav.update('board', identifier, action='destination', candidate=1, location=LOCATION)['phase'] == 'guiding'
    assert provider.calls.count(('route', 'car')) == 1


def test_off_route_requires_multiple_fixes_and_reroute_has_cooldown(tmp_path):
    nav, provider, now, identifier = fixture(tmp_path)
    nav.update('board', identifier, action='mode', mode='foot', location=LOCATION)
    away = {**LOCATION, 'longitude': ORIGIN[0]+.002}
    now[0] += 21
    for i in range(3):
        result = nav.update('board', identifier, location=away)
        if i < 2: assert result['phase'] == 'off_route'
        now[0] += 2
    assert provider.calls.count(('route', 'foot')) == 2
    assert result['cue'] == ''
    assert nav.update('board', identifier, location=None)['phase'] == 'gps_waiting'


def test_failure_waits_for_retry_instead_of_hammering_provider(tmp_path):
    nav, provider, _, identifier = fixture(tmp_path)
    provider.fail = True
    assert nav.update('board', identifier, action='mode', mode='car', location=LOCATION)['phase'] == 'unavailable'
    before = len(provider.calls)
    for _ in range(5): assert nav.update('board', identifier, location=LOCATION)['phase'] == 'unavailable'
    assert len(provider.calls) == before
    provider.fail = False
    assert nav.update('board', identifier, action='retry', location=LOCATION)['phase'] == 'guiding'


def test_malformed_destination_provider_pauses_guidance_until_retry(tmp_path):
    providers = Providers(tmp_path, transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[])))
    nav = Navigation(tmp_path, providers)
    identifier = nav.start('board', 'Museo de prueba', 'exchange-1')
    try:
        state = nav.update('board', identifier, action='mode', mode='foot', location=LOCATION)
        assert state['phase'] == 'unavailable' and not state['cue']
        assert nav.update('board', identifier, location=LOCATION)['phase'] == 'unavailable'
    finally:
        nav.close()
    assert providers.client.is_closed


def test_progress_cue_arrival_cancel_and_new_session(tmp_path):
    nav, _, now, identifier = fixture(tmp_path)
    nav.update('board', identifier, action='mode', mode='foot', location=LOCATION)
    close = {**LOCATION, 'latitude': ORIGIN[1]+.0008}
    result = nav.update('board', identifier, location=close)
    assert result['cue'] == 'ahead_right' and result['cue_seq'] == 1
    assert nav.update('board', identifier, location=close)['cue_seq'] == 1
    at_end = {**LOCATION, 'latitude': END[1]}
    assert nav.update('board', identifier, location=at_end)['phase'] == 'guiding'
    now[0] += 2
    assert nav.update('board', identifier, location=at_end)['phase'] == 'arrived'
    assert nav.status('board')['cue'] == 'arrive'
    other = nav.start('board', 'Otra plaza', 'exchange-2')
    assert other != identifier and nav.status('board', identifier)['phase'] == 'cancelled'
    assert nav.status('board')['id'] == other and nav.status('board')['phase'] == 'choose_mode'
    nav.cancel('board')
    assert nav.status('board')['phase'] == 'cancelled'


def test_map_codec_tile_cache_and_private_public_contract(tmp_path):
    nav, _, _, identifier = fixture(tmp_path)
    state = nav.update('board', identifier, action='mode', mode='foot', location=LOCATION)
    encoded = nav.map('board', identifier, state['map_revision'])
    magic, version, rle, width, height = struct.unpack('<4sBBHH', encoded[:10])
    assert (magic, version, width, height) == (b'MMAP', 1, WIDTH, HEIGHT)
    assert len(encoded) <= 10+WIDTH*HEIGHT*2
    if rle: assert sum(struct.unpack('<HH', encoded[i:i+4])[0] for i in range(10, len(encoded), 4)) == WIDTH*HEIGHT
    assert nav.map('board', identifier, state['map_revision']) == encoded
    assert 'position' not in state and 'geometry' not in state
    with pytest.raises(KeyError): nav.map('board', identifier, state['map_revision']+1)


def test_provider_uses_actual_foot_and_car_graphs_and_caches_tiles(tmp_path, monkeypatch):
    requests = []
    def respond(request):
        requests.append(request)
        assert request.headers['user-agent'].startswith('MochiNavigation/')
        if request.url.path.endswith('.png'):
            from io import BytesIO
            buffer = BytesIO(); Image.new('RGB', (256,256)).save(buffer, 'PNG')
            return httpx.Response(200, content=buffer.getvalue(), headers={'content-type': 'image/png'})
        route = {'duration': 180, 'geometry': {'coordinates': [ORIGIN, END]},
                 'legs': [{'steps': [{'maneuver': {'type':'depart','location':ORIGIN}},
                                    {'maneuver': {'type':'arrive','location':END}}]}]}
        return httpx.Response(200, json={'code':'Ok', 'routes':[route], 'waypoints':[{'distance':0}]})
    monkeypatch.setattr('navigation.time.sleep', lambda _: None)
    provider = Providers(tmp_path, transport=httpx.MockTransport(respond))
    provider.route(ORIGIN, END, 'foot'); provider.route(ORIGIN, END, 'car')
    assert '/routed-foot/' in requests[0].url.path and '/routed-car/' in requests[1].url.path
    provider.tile(16, 100, 100); provider.tile(16, 100, 100)
    assert len(requests) == 3


def test_legacy_json_and_audio_cue_expiry_auth_and_scope(tmp_path):
    nav = Navigation(tmp_path, FakeProviders())
    brain = Brain()
    client = TestClient(create_app(Settings(TOKEN,tmp_path,tmp_path/'voice',navigation_enabled=True), brain, Speech(), navigation=nav))
    headers = {**HEADERS, 'X-Device-ID':'board'}
    body = {'text':'¿Cómo ir al museo?', 'device_id':'board', 'exchange_id':'navigation-retry'}
    response = client.post('/v1/chat', headers=headers, json=body)
    assert response.status_code == 200 and set(response.json()) == {'text','emotion'}
    identifier = response.headers['X-Mochi-Navigation']
    assert client.post('/v1/chat',headers=headers,json=body).headers['X-Mochi-Navigation'] == identifier
    assert brain.calls == []
    assert client.get('/v1/navigation/active').status_code == 401
    assert client.get('/v1/navigation/active',headers={**HEADERS,'X-Device-ID':'other'}).status_code == 404
    assert client.post(f'/v1/navigation/{identifier}',headers=headers,json={'action':'mode','mode':'flying'}).status_code == 422
    result = client.post(f'/v1/navigation/{identifier}',headers=headers,json={'action':'mode','mode':'foot','location':LOCATION})
    assert result.json()['phase'] == 'guiding'
    assert client.post(f'/v1/navigation/{identifier}/audio',headers=headers,json={'sequence':1,'cue':'right'}).status_code == 409
    near = {**LOCATION,'latitude':ORIGIN[1]+.0008}
    result = client.post(f'/v1/navigation/{identifier}',headers=headers,json={'location':near}).json()
    assert result['cue'] == 'ahead_right'
    # Ask the existing /say endpoint to prepare one clip with the active voice.
    assert client.post('/v1/say',headers=headers,json={'text':CUES['ahead_right']}).status_code == 200
    cue = client.post(f'/v1/navigation/{identifier}/audio',headers=headers,json={'sequence':result['cue_seq'],'cue':'ahead_right'})
    assert cue.status_code == 200 and cue.headers['X-Mochi-Stream'] == 'pcm16'
    assert client.post(f'/v1/navigation/{identifier}',headers=headers,json={}).json()['phase'] == 'gps_waiting'
    assert client.post(f'/v1/navigation/{identifier}/audio',headers=headers,json={'sequence':result['cue_seq'],'cue':'right'}).status_code == 409
