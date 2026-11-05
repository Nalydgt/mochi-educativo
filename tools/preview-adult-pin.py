"""Layout preview from the numeric PIN map; not a physical device capture."""
import json
from pathlib import Path
import re
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'firmware/main/mochi_education.c').read_text(encoding='utf-8')
width, height = map(int, re.search(r'lv_obj_set_size\(keyboard, (\d+), (\d+)\)', source).groups())
assert 'lv_obj_center(keyboard);' in source
keys = re.search(r'pin_keys\[\] = \{(.+?)\};', source, re.S)[1]
digits = re.findall(r'"(\d+)"', keys)
assert set(digits) == set('0123456789') and len(digits) == 10
out = ROOT / 'docs/mediciones/20261106-mochi-adult-pin'
out.mkdir(parents=True, exist_ok=True)
image = Image.new('RGB', (466, 466), '#111111')
draw = ImageDraw.Draw(image)
font = lambda size: ImageFont.truetype(str(ROOT / 'tools/fonts/Montserrat-Medium.ttf'), size)
def text(value, x, y, size=16):
    draw.text((x, y), value, anchor='mm', font=font(size), fill='#E4EBE3')
draw.ellipse((0, 0, 465, 465), fill='black', outline='#484848', width=2)
text('Renovar vínculo', 233, 62)
draw.rounded_rectangle((118, 86, 348, 128), 10, fill='#101010', outline='#484848')
text('PIN de adulto', 233, 107)
x0, y0 = (466 - width) / 2, (466 - height) / 2
for index, value in enumerate(['1','2','3','4','5','6','7','8','9','<','0','OK']):
    row, column = divmod(index, 3)
    left, top = x0 + column * (width + 6) / 3, y0 + row * (height + 6) / 4
    right, bottom = left + (width - 12) / 3, top + (height - 18) / 4
    draw.rounded_rectangle((left, top, right, bottom), 12, fill='#101010', outline='#484848')
    text(value, (left + right) / 2, (top + bottom) / 2, 20)
for center, caption in [(160, 'Confirmar'), (306, 'Cancelar')]:
    draw.rounded_rectangle((center - 66, 372, center + 66, 416), 12, fill='#101010', outline='#484848')
    text(caption, center, 394)
image.save(out / 'pin-centered.png')
(out / 'report.json').write_text(json.dumps({'physicalScreenshot': False, 'source': 'numeric C map and keyboard dimensions',
    'center': [x0 + width / 2, y0 + height / 2], 'digitsOnly': True, 'minimumKeyHeight': (height - 18) / 4,
    'font': 'Host TTF approximation'}, indent=2) + '\n')
print(json.dumps({'preview': str(out / 'pin-centered.png'), 'digitsOnly': True, 'center': [233,233]}))
