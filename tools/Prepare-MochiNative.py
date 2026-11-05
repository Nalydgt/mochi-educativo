"""Keep native-size Coucou artwork in full RGB565 with an eight-bit alpha plane."""
from pathlib import Path
import hashlib,json
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
base=ROOT/'firmware/assets/mochi-native'
manifest=json.loads((base/'rendered.json').read_text(encoding='utf-8'))
matrix=np.array([[0,8,2,10],[12,4,14,6],[3,11,1,9],[15,7,13,5]],dtype=np.uint16)
lines=['/* Original Coucou artwork at native pixel size; generated, no palette quantization. */']
for asset in manifest['assets']:
    pixels=np.array(Image.open(base/asset['file']).convert('RGBA'),dtype=np.uint16)
    h,w=pixels.shape[:2];yy,xx=np.mgrid[:h,:w]
    threshold=matrix[(yy+asset['y'])%4,(xx+asset['x'])%4]*16+8
    r=(pixels[:,:,0]*31+threshold)//255
    g=(pixels[:,:,1]*63+threshold)//255
    b=(pixels[:,:,2]*31+threshold)//255
    colour=((r<<11)|(g<<5)|b).astype('<u2').tobytes()
    alpha=pixels[:,:,3].astype('uint8').tobytes()
    data=colour+alpha
    target=base/(asset['id']+'.rgb565a8');target.write_bytes(data)
    asset.update(binary=target.name,size=len(data),sha256=hashlib.sha256(data).hexdigest())
    name=asset['id']
    lines.append(f'extern const uint8_t native_{name}[] asm("_binary_native_{name}_start");')
lines.append('static const native_asset_t native_assets[] = {')
for a in manifest['assets']:
    lines.append('    {"%s",%d,%d,{.header={.magic=LV_IMAGE_HEADER_MAGIC,.cf=LV_COLOR_FORMAT_RGB565A8,.w=%d,.h=%d,.stride=%d},.data_size=%d,.data=native_%s}},'%
                 (a['id'],a['x'],a['y'],a['width'],a['height'],a['width']*2,a['size'],a['id']))
lines.append('};')
(ROOT/'firmware/main/mochi_native_index.inc').write_text('\n'.join(lines)+'\n',encoding='utf-8')
(base/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'layers':len(manifest['assets']),'bytes':sum(a['size'] for a in manifest['assets']),'runtime_scale':1.0}))
