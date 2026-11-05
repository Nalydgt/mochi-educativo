"""Local, durable navigation state. OSM services supply facts, never the LLM.

Only the latest position is kept: this is not a GPS track recorder. Public
providers are configurable; their cache/rate policies also apply on the NAS.
"""
from __future__ import annotations

from bisect import bisect_right
from contextlib import contextmanager
from io import BytesIO
import json
import math
from pathlib import Path
import re
import sqlite3
import struct
import threading
import time
import unicodedata
import uuid

import httpx
from PIL import Image, ImageDraw

UA = 'MochiNavigation/0.11 (+https://github.com/Nalydgt)'
ATTRIBUTION = '© OpenStreetMap contributors'
FIX_MAP = 'https://www.openstreetmap.org/fixthemap'
WIDTH, HEIGHT = 384, 224
CUES = {
    'left': 'Gira a la izquierda.', 'right': 'Gira a la derecha.',
    'slight_left': 'Mantente a la izquierda.', 'slight_right': 'Mantente a la derecha.',
    'straight': 'Continúa recto.', 'uturn': 'Da la vuelta cuando sea posible.',
    'roundabout': 'Entra en la rotonda y sigue la salida indicada en pantalla.',
    'arrive': 'Has llegado a tu destino.',
    'reroute': 'Te has desviado. Estoy recalculando la ruta.',
}
for _exit in range(1, 9):
    CUES[f'exit_{_exit}'] = f'En la rotonda, toma la salida {_exit}.'
for _key, _text in list(CUES.items()):
    if _key not in {'arrive', 'reroute'}:
        CUES['ahead_'+_key] = 'Más adelante: '+_text[0].lower()+_text[1:]


@contextmanager
def database(path):
    db = sqlite3.connect(path, timeout=15)
    try:
        with db: yield db
    finally: db.close()


def fold(text):
    return ''.join(c for c in unicodedata.normalize('NFD', text.lower()) if not unicodedata.combining(c))


def intent(text):
    """Conservative Spanish commands; ordinary knowledge stays with the brain."""
    normalized = fold(text).strip(' ¿?¡!.,')
    if re.fullmatch(r'(?:mochi[, ]+)?(?:cancela|termina|para|deten)(?:r)? (?:la )?(?:ruta|navegacion|guia)', normalized):
        return ('cancel', '')
    match = re.search(r'\b(?:como (?:puedo )?(?:ir|llegar)|(?:llevame|guiame)|(?:inicia|empieza) (?:una )?ruta|quiero ir)\s+(?:hasta\s+|a\s+|al\s+)(.+)', text, re.I)
    if not match:
        # Match accents without losing the original destination spelling.
        match = re.search(r'\b(?:como (?:puedo )?(?:ir|llegar)|llevame|guiame|(?:inicia|empieza) (?:una )?ruta|quiero ir)\s+(?:hasta\s+|a\s+|al\s+)(.+)', fold(text))
    if not match: return None
    destination = text[match.start(1):].strip(' ¿?¡!.,')[:180]
    if not destination or re.match(r'^(?:ser |hacer |saber |entender |programar |un acuerdo|una conclusion|fin de mes)', fold(destination)):
        return None
    return ('start', destination)


def number(value, lower, upper):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lower <= value <= upper:
        raise ValueError('invalid_navigation_data')
    return float(value)


def point(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2: raise ValueError('invalid_coordinate')
    return [number(value[0], -180, 180), number(value[1], -85.0511287, 85.0511287)]


def fresh(location):
    if location is None: return None
    data = location.model_dump() if hasattr(location, 'model_dump') else location
    if data.get('current') is not True or not 0 <= data.get('age_seconds', -1) <= 10: return None
    return point([data['longitude'], data['latitude']])


def distance(a, b):
    lat = math.radians((a[1] + b[1]) / 2)
    return math.hypot(math.radians(a[0] - b[0]) * math.cos(lat), math.radians(a[1] - b[1])) * 6371008.8


def project(p, zoom):
    size = 256 * 2**zoom
    lat = math.radians(max(-85.0511287, min(85.0511287, p[1])))
    return ((p[0] + 180) / 360 * size, (1 - math.asinh(math.tan(lat)) / math.pi) / 2 * size)


def nearest(p, geometry, start=0, stop=None):
    """Point-to-segment projection in a local metre plane, returning progress."""
    best = (float('inf'), start, 0.0)
    scale = math.cos(math.radians(p[1]))
    for index in range(max(0, start), min(len(geometry) - 1, stop or len(geometry))):
        a, b = geometry[index:index + 2]
        ax, ay = (a[0] - p[0]) * scale, a[1] - p[1]
        dx, dy = (b[0] - a[0]) * scale, b[1] - a[1]
        length = dx * dx + dy * dy
        fraction = max(0., min(1., -(ax * dx + ay * dy) / length)) if length else 0.
        metres = math.hypot(ax + fraction * dx, ay + fraction * dy) * 111195.08
        if metres < best[0]: best = (metres, index, fraction)
    return best


def maneuver(step):
    data = step['maneuver']
    kind, modifier = data.get('type', ''), data.get('modifier', 'straight').replace(' ', '_')
    if kind == 'arrive': return 'arrive', 'Llegada al destino'
    if kind in {'roundabout', 'rotary'}:
        exit_number = data.get('exit')
        if isinstance(exit_number, int) and 1 <= exit_number <= 8:
            return f'exit_{exit_number}', f'Rotonda: salida {exit_number}'
        return 'roundabout', 'Sigue la salida de la ruta en la rotonda'
    cue = modifier if modifier in CUES else 'left' if modifier == 'sharp_left' else 'right' if modifier == 'sharp_right' else 'straight'
    text = CUES[cue].rstrip('.')
    if kind == 'depart': text = 'Inicia la marcha por la ruta'
    name = str(step.get('name') or step.get('ref') or '')[:90]
    return cue, text + (f' · {name}' if name else '')


class Unavailable(Exception):
    pass


class Providers:
    def __init__(self, directory, *, photon='https://photon.komoot.io/api/',
                 router='https://routing.openstreetmap.de', tiles='https://tile.openstreetmap.org', transport=None):
        self.photon, self.router, self.tiles = photon.rstrip('/'), router.rstrip('/'), tiles.rstrip('/')
        self.client = httpx.Client(timeout=12, follow_redirects=False, transport=transport,
                                   headers={'User-Agent': UA, 'Accept-Language': 'es'})
        self.db = Path(directory) / 'navigation-cache.sqlite3'
        with database(self.db) as db:
            db.execute('CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, expires REAL, accessed REAL, value BLOB)')
        self.network_lock = threading.Lock()
        self.last_request = 0.

    def close(self):
        self.client.close()

    def get(self, url, params=None, *, ttl=0, image=False):
        key = str(httpx.URL(url, params=params))
        with database(self.db) as db:
            row = db.execute('SELECT expires,value FROM cache WHERE key=?', (key,)).fetchone()
            if row and row[0] > time.time():
                db.execute('UPDATE cache SET accessed=? WHERE key=?', (time.time(), key))
                return row[1] if image else json.loads(row[1])
        try:
            with self.network_lock:
                time.sleep(max(0, 1.05 - (time.monotonic() - self.last_request)))
                self.last_request = time.monotonic()
                with self.client.stream('GET', url, params=params) as response:
                    response.raise_for_status()
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > (512000 if image else 8_000_000): raise Unavailable()
                    if image:
                        if not response.headers.get('content-type', '').startswith('image/png'): raise Unavailable()
                        max_age = re.search(r'max-age=(\d+)', response.headers.get('cache-control', ''))
                        ttl = max(604800, int(max_age[1]) if max_age else 0)
            if ttl:
                with database(self.db) as db:
                    db.execute('INSERT OR REPLACE INTO cache VALUES (?,?,?,?)', (key, time.time()+ttl, time.time(), bytes(body)))
                    db.execute('DELETE FROM cache WHERE key IN (SELECT key FROM cache ORDER BY accessed DESC LIMIT -1 OFFSET 1024)')
            return bytes(body) if image else json.loads(body)
        except (httpx.HTTPError, ValueError, KeyError, OSError):
            # Do not include URLs/precise locations in application logs/errors.
            raise Unavailable('navigation_provider_unavailable') from None

    def search(self, query, position):
        data = self.get(self.photon, {'q': query, 'lon': position[0], 'lat': position[1], 'limit': 3}, ttl=86400)
        results = []
        for feature in data.get('features', [])[:3]:
            coordinates = point(feature['geometry']['coordinates'])
            props = feature['properties']
            parts = list(dict.fromkeys(str(props.get(k) or '').strip() for k in ('name', 'street', 'housenumber', 'city', 'state', 'country')))
            label = ', '.join(part for part in parts if part)[:160]
            if label and not any(distance(coordinates, r['point']) < 10 and label == r['label'] for r in results):
                results.append({'label': label, 'point': coordinates})
        return results

    def route(self, origin, destination, mode):
        profile = 'routed-foot' if mode == 'foot' else 'routed-car'
        coordinates = ';'.join(f'{p[0]:.6f},{p[1]:.6f}' for p in (origin, destination))
        data = self.get(f'{self.router}/{profile}/route/v1/driving/{coordinates}',
                        {'overview': 'full', 'geometries': 'geojson', 'steps': 'true', 'generate_hints': 'false'})
        if data.get('code') != 'Ok' or not data.get('routes'): raise Unavailable('no_route')
        for waypoint in data.get('waypoints', []):
            if number(waypoint.get('distance', 0), 0, 100000) > 150: raise Unavailable('road_too_far')
        route = data['routes'][0]
        raw = route['geometry']['coordinates']
        if not 2 <= len(raw) <= 50000: raise Unavailable('route_too_large')
        geometry = [point(p) for p in raw]
        cumulative = [0.]
        for a, b in zip(geometry, geometry[1:]): cumulative.append(cumulative[-1] + distance(a, b))
        if cumulative[-1] > 2_000_000: raise Unavailable('route_too_large')
        steps, prior_index = [], 0
        for leg in route['legs']:
            for step in leg['steps']:
                p = point(step['maneuver']['location'])
                _, index, fraction = nearest(p, geometry, prior_index)
                prior_index = index
                cue, instruction = maneuver(step)
                steps.append({'at': cumulative[index] + fraction*(cumulative[index+1]-cumulative[index]),
                              'cue': cue, 'instruction': instruction})
        if not steps or len(steps) > 2000: raise Unavailable('invalid_steps')
        return {'geometry': geometry, 'cumulative': cumulative, 'steps': steps,
                'duration': number(route['duration'], 0, 10_000_000), 'length': cumulative[-1]}

    def tile(self, z, x, y):
        if not 0 <= y < 2**z: return Image.new('RGB', (256, 256), '#e5e7eb')
        raw = self.get(f'{self.tiles}/{z}/{x % 2**z}/{y}.png', image=True)
        with Image.open(BytesIO(raw)) as source:
            if source.size != (256, 256): raise Unavailable('invalid_tile')
            return source.convert('RGB')


def encode_map(image):
    """Bounded little-endian RGB565, with RLE only when it saves bytes."""
    rgb = image.convert('RGB').tobytes()
    pixels = zip(rgb[0::3], rgb[1::3], rgb[2::3])
    colours = [((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3) for r, g, b in pixels]
    raw = struct.pack(f'<{len(colours)}H', *colours)
    runs, previous, count = bytearray(), colours[0], 0
    for colour in colours:
        if colour != previous or count == 65535:
            runs.extend(struct.pack('<HH', count, previous)); count = 0; previous = colour
        count += 1
    runs.extend(struct.pack('<HH', count, previous))
    compressed = len(runs) < len(raw)
    return struct.pack('<4sBBHH', b'MMAP', 1, int(compressed), image.width, image.height) + (runs if compressed else raw)


class Navigation:
    def __init__(self, directory, providers=None, clock=time.time):
        self.path = Path(directory) / 'navigation.sqlite3'
        self.lock, self.clock = threading.RLock(), clock
        self.providers = providers or Providers(directory)
        self.frames = {}
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, device TEXT, exchange_id TEXT UNIQUE, state TEXT, updated REAL)')
            db.execute('CREATE INDEX IF NOT EXISTS nav_device ON sessions(device,updated)')

    def db(self):
        return database(self.path)

    def close(self):
        close = getattr(self.providers, 'close', None)
        if callable(close): close()

    def save(self, state):
        with self.db() as db:
            db.execute('INSERT OR REPLACE INTO sessions VALUES (?,?,?,?,?)',
                       (state['id'], state['device'], state['exchange_id'], json.dumps(state, ensure_ascii=False), self.clock()))
            # A single current state per device; retain retry IDs for seven days.
            db.execute('DELETE FROM sessions WHERE updated<?', (self.clock() - 7*86400,))

    def load(self, device, identifier=None):
        with self.db() as db:
            row = db.execute('SELECT state FROM sessions WHERE device=?' + (' AND id=?' if identifier else '') + ' ORDER BY updated DESC,rowid DESC LIMIT 1',
                             (device, identifier) if identifier else (device,)).fetchone()
        if not row: raise KeyError('unknown_navigation')
        return json.loads(row[0])

    def for_exchange(self, device, exchange):
        with self.db() as db:
            row = db.execute('SELECT id FROM sessions WHERE device=? AND exchange_id=?', (device, exchange)).fetchone()
        return row[0] if row else None

    def status(self, device, identifier=None):
        with self.lock: return self.public(self.load(device, identifier))

    def start(self, device, query, exchange, location=None):
        with self.lock:
            existing = self.for_exchange(device, exchange)
            if existing: return existing
            # End the previous session before creating another, including on restart.
            try:
                previous = self.load(device)
                previous['phase'] = 'cancelled'; self.save(previous)
            except KeyError: pass
            identifier = uuid.uuid4().hex
            self.save({'id': identifier, 'device': device, 'exchange_id': exchange, 'query': query,
                       'phase': 'choose_mode', 'mode': '', 'candidates': [], 'selected': None,
                       'route': None, 'progress': 0, 'index': 0, 'off_count': 0, 'last_reroute': 0,
                       'cue_seq': 0, 'cue': '', 'announced': -1, 'last_fix': 0,
                       'position': None, 'map_revision': 0, 'message': 'Elige cómo vas a ir'})
            return identifier

    def cancel(self, device):
        with self.lock:
            try:
                state = self.load(device); state['phase'] = 'cancelled'; state['cue'] = ''; self.save(state)
            except KeyError: pass

    def build_route(self, state, p):
        state['last_reroute'] = self.clock()
        route = self.providers.route(p, state['selected']['point'], state['mode'])
        state.update(route=route, phase='guiding', progress=0, index=0, off_count=0,
                     announced=-1, cue='', message='', arrival_count=0)
        state['map_revision'] += 1
        state['route_generation'] = state.get('route_generation', 0)+1
        state.pop('map_center', None)

    def update(self, device, identifier=None, *, location=None, action='', mode='', candidate=None, simulation=False):
        with self.lock:
            state = self.load(device, identifier)
            state['simulation'] = bool(simulation)
            if action == 'cancel':
                state.update(phase='cancelled', cue=''); self.save(state); return self.public(state)
            if state['phase'] in {'cancelled', 'arrived'}: return self.public(state)
            if state['phase'] == 'unavailable' and action not in {'retry','mode','destination'}:
                return self.public(state)
            if action == 'retry': state['route'] = None
            if action == 'mode':
                if mode not in {'foot', 'car'}: raise ValueError('invalid_travel_mode')
                if state['mode'] and state['mode'] != mode:
                    state.update(route=None, selected=None, candidates=[])
                state.update(mode=mode, phase='gps_waiting')
            if action == 'destination':
                if not isinstance(candidate, int) or not 0 <= candidate < len(state['candidates']) or (
                    state['phase'] != 'choose_destination' and state['selected'] != state['candidates'][candidate]):
                    raise ValueError('invalid_destination')
                state.update(selected=state['candidates'][candidate], phase='gps_waiting')
            if not state['mode']: return self.public(state)
            p = fresh(location)
            if p is None:
                if state['phase'] != 'choose_destination': state['phase'] = 'gps_waiting'
                state['message'] = 'Buscando GPS. Sal al exterior'; state['cue'] = ''
                self.save(state); return self.public(state)
            if state['position'] and self.clock()-state['last_fix'] >= 1:
                state['speed'] = min(55 if state['mode']=='car' else 5,
                    distance(p,state['position']) / (self.clock()-state['last_fix']))
            state['position'], state['last_fix'] = p, self.clock()
            try:
                if not state['candidates']:
                    state['candidates'] = self.providers.search(state['query'], p)
                    if not state['candidates']: raise Unavailable('destination_not_found')
                    if len(state['candidates']) == 1: state['selected'] = state['candidates'][0]
                if state['selected'] is None:
                    state.update(phase='choose_destination', message='Elige el destino')
                else:
                    if not state['route']: self.build_route(state, p)
                    self.advance(state, p)
            except (Unavailable, ValueError, KeyError, TypeError, IndexError, AttributeError):
                state.update(phase='unavailable', cue='', message='No se pudo calcular la ruta. Pulsa Reintentar')
            self.save(state)
            return self.public(state)

    def advance(self, state, p):
        route = state['route']
        lateral, index, fraction = nearest(p, route['geometry'], max(0, state['index']-8), state['index']+300)
        limit = 55 if state['mode'] == 'car' else 35
        # Count independently sampled fixes, never repeated HTTP polls of one fix.
        now = self.clock()
        if now - state.get('sampled_at', 0) >= 1.5:
            state['off_count'] = state['off_count']+1 if lateral > limit else 0
            state['sampled_at'] = now
        if lateral > limit:
            state.update(phase='off_route', message='Fuera de ruta · recalculando', cue='')
            if state['off_count'] >= 3 and now-state['last_reroute'] >= 20:
                self.build_route(state, p)
            return
        state.update(phase='guiding', message='', index=max(state['index'], index))
        progress = route['cumulative'][index] + fraction*(route['cumulative'][index+1]-route['cumulative'][index])
        state['progress'] = max(state['progress'], progress)
        remaining = max(0, route['length']-state['progress'])
        if remaining < 25 and distance(p, route['geometry'][-1]) < 30:
            state['arrival_count'] = state.get('arrival_count', 0)+1
            if state['arrival_count'] >= 2:
                state.update(phase='arrived', cue='arrive', message='Has llegado'); state['cue_seq'] += 1
                return
        else: state['arrival_count'] = 0
        step_index = min(len(route['steps'])-1, max(1, bisect_right([s['at'] for s in route['steps']], state['progress']+5)))
        step = route['steps'][step_index]
        state.update(next_step=step_index, turn_metres=max(0, step['at']-state['progress']), instruction=step['instruction'], arrow=step['cue'])
        # Audio is a pre-recorded generic cue. Exact distance/street stays visible.
        speed = state.get('speed', 0)
        threshold = max(180, speed*12) if state['mode']=='car' else 45
        immediate = max(35, speed*4) if state['mode']=='car' else 12
        stage = step_index*2 + int(state['turn_metres'] <= immediate)
        if state['turn_metres'] <= threshold and stage > state['announced'] and step['cue'] != 'arrive':
            cue = step['cue'] if state['turn_metres'] <= immediate else 'ahead_'+step['cue']
            state.update(announced=stage, cue=cue); state['cue_seq'] += 1
        center = state.get('map_center')
        if center is None or distance(center, p) > (100 if state['mode']=='car' else 25):
            state['map_center'] = p; state['map_revision'] += 1

    def public(self, state):
        # A process restart or a lost connection must never present saved GPS as live.
        stale = self.clock() - state['last_fix'] > 10
        phase = state['phase']
        if stale and phase in {'guiding', 'off_route'}: phase = 'gps_waiting'
        route = state['route']
        remaining = max(0, route['length']-state['progress']) if route else 0
        center = state.get('map_center') or state['position']
        zoom = 16 if state['mode']=='car' else 17
        world = project(center, zoom) if center else (0, 0)
        return {'id': state['id'], 'phase': phase, 'mode': state['mode'],
                'simulation': state.get('simulation', False),
                'destination': (state['selected'] or {}).get('label', state['query']),
                'candidates': [c['label'] for c in state['candidates']],
                'instruction': state.get('instruction', ''), 'arrow': state.get('arrow', 'straight'),
                'message': 'Buscando GPS. Sal al exterior' if stale and phase=='gps_waiting' else state['message'],
                'turn_metres': round(state.get('turn_metres', 0)), 'remaining_metres': round(remaining),
                'remaining_seconds': round(route['duration']*remaining/max(1, route['length'])) if route else 0,
                'cue_seq': state['cue_seq'], 'cue': state['cue'] if (not stale and phase in {'guiding','arrived'}) else '',
                'map_revision': state['map_revision'], 'map_x': round(world[0]-WIDTH/2),
                'route_generation': state.get('route_generation', 0),
                'map_y': round(world[1]-HEIGHT/2), 'map_zoom': zoom,
                'attribution': ATTRIBUTION, 'fix_map_url': FIX_MAP}

    def map(self, device, identifier, revision):
        with self.lock:
            state = self.load(device, identifier)
            if revision != state['map_revision'] or not state.get('map_center') or not state['route']:
                raise KeyError('map_not_ready')
            cached = self.frames.get(identifier)
            if cached and cached[0] == revision: return cached[1]
            public = self.public(state)
            z, left, top = public['map_zoom'], public['map_x'], public['map_y']
            geometry = state['route']['geometry']
        # Fetch only tiles intersecting the displayed rectangle. No prefetch.
        image = Image.new('RGB', (WIDTH, HEIGHT), '#e5e7eb')
        for y in range(top//256, (top+HEIGHT-1)//256+1):
            for x in range(left//256, (left+WIDTH-1)//256+1):
                image.paste(self.providers.tile(z, x, y), (x*256-left, y*256-top))
        draw = ImageDraw.Draw(image)
        path = [(x-left, y-top) for x,y in (project(p,z) for p in geometry)]
        draw.line(path, fill='white', width=9)
        draw.line(path, fill='#1769e8', width=5)
        encoded = encode_map(image)
        with self.lock:
            self.frames = {identifier: (revision, encoded)}
        return encoded
