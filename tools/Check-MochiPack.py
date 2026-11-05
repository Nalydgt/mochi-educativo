"""Verify native artwork integrity and catalogue coverage against pinned Coucou."""
from pathlib import Path
import hashlib,json,re
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
base=ROOT/'firmware/assets/mochi-native'
art=json.loads((base/'manifest.json').read_text(encoding='utf-8'))
catalogue=json.loads((ROOT/'firmware/assets/mochi/native-catalog.json').read_text(encoding='utf-8'))
source=ROOT/'.references/coucou-latest/windows/src/mochi'
engine=(source/'engine.ts').read_text(encoding='utf-8')
states_block=engine[engine.index('export const BOT_STATES'):engine.index('/** State')]
states=set(re.findall(r'^  (\w+): \{',states_block,re.M))
emote_block=engine[engine.index('const EMOTE_EYE'):]
emote_block=emote_block[:emote_block.index('};')]
emotes=set(re.findall(r'(\w+): "\w+"',emote_block))
wardrobe=(source/'wardrobe.ts').read_text(encoding='utf-8')
outfit_block=wardrobe[wardrobe.index('export const OUTFIT_SELECTIONS'):]
outfits=set(re.findall(r'"(\w+)"',outfit_block[:outfit_block.index('] as const;')]))-{'auto','none'}
groups={kind:{r['id'] for r in catalogue['animations'] if r['group']==kind}
        for kind in ('state','emote','mini','outfit','gesture')}
assert groups['state']==states
assert groups['emote']==emotes
assert groups['mini']=={'mini_'+name for name in emotes}
assert groups['outfit']=={'outfit_'+name for name in outfits}
assert len(groups['gesture'])==10 and len(catalogue['animations'])==46
assert art['commit']==catalogue['commit'] and art['radius']==120
assert {a['outfit'] for a in art['assets']}-{'none'}==outfits
assert len(art['assets'])==14
index=(ROOT/'firmware/main/mochi_native_index.inc').read_text(encoding='utf-8')
renderer=(ROOT/'firmware/main/mochi_animation.c').read_text(encoding='utf-8')
alpha_edges=0
for asset in art['assets']:
    data=(base/asset['binary']).read_bytes()
    assert len(data)==asset['size']==asset['width']*asset['height']*3
    assert hashlib.sha256(data).hexdigest()==asset['sha256']
    assert 'native_'+asset['id'] in index
    assert asset['width']%2==0
    with Image.open(base/asset['file']) as image:
        assert image.size==(asset['width'],asset['height'])
        alpha=np.array(image.convert('RGBA'))[:,:,3]
    assert data[asset['width']*asset['height']*2:]==alpha.tobytes()
    assert np.any(alpha==0) and np.any(alpha==255)
    if asset['kind']=='body':
        # The native body keeps exact antialiasing in a small internal mask.
        # Its opaque interior must be contiguous; costume layers remain full images.
        assert int(np.count_nonzero((alpha>0)&(alpha<255)))<=4096-216*10
        for row in alpha:
            opaque=np.flatnonzero(row==255)
            if opaque.size:assert np.all(row[opaque[0]:opaque[-1]+1]==255)
    alpha_edges+=int(np.count_nonzero((alpha>0)&(alpha<255)))
for clip in catalogue['animations']:
    assert '"'+clip['id']+'"' in renderer
    assert clip['duration_ms']>0
assert 'lv_gif_' not in renderer and 'lv_gif_create' not in renderer
report={'passed':True,'native_resolution':True,'renderer':'native','catalogue_entries':46,
        'states':len(states),'expressions':len(emotes),'outfits':len(outfits),'layers':len(art['assets']),
        'embedded_bytes':sum(a['size'] for a in art['assets']),'antialiased_edge_pixels':alpha_edges}
(ROOT/'.runtime').mkdir(exist_ok=True)
(ROOT/'.runtime/coucou-pack-check.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
