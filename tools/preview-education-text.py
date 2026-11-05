"""Static layout QA, using the C keyboard map and bounds; not a device capture."""
import json
from pathlib import Path
import re
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / 'firmware/main/mochi_education_text.c').read_text(encoding='utf-8')
output = ROOT / 'docs/mediciones/20261106-mochi-text-layout'
output.mkdir(parents=True, exist_ok=True)
font_path = ROOT / 'tools/fonts/Montserrat-Medium.ttf'
font = lambda size: ImageFont.truetype(str(font_path), size)
width, height = map(int, re.search(r'lv_obj_set_size\(keys, (\d+), (\d+)\)', source).groups())
top = int(re.search(r'lv_obj_align\(keys, LV_ALIGN_TOP_MID, 0, (\d+)\)', source)[1])
keyboard = re.search(r'lower_keys\[\] = \{(.+?)\};', source, re.S)[1]
items = [json.loads(match[0]) if match[0].startswith('"') else '<' for match in re.finditer(r'"(?:\\.|[^"\\])*"|LV_SYMBOL_BACKSPACE', keyboard)]
rows, current = [], []
for item in items:
    if item in ('\n', ''):
        rows.append(current); current = []
    else:
        current.append(item)
weights = {int(index): int(value) for index, value in re.findall(r'lv_buttonmatrix_set_button_width\(keys, (\d+), (\d+)\)', source)}
image = Image.new('RGB', (466, 466), '#131D18')
draw = ImageDraw.Draw(image)
draw.ellipse((0, 0, 465, 465), fill='black', outline='#47634F', width=2)
def center(text, x, y, size=16, color='#E4EBE3'):
    draw.text((x, y), text, font=font(size), fill=color, anchor='mm')
center('Escribir a Mochi', 233, 88, 20)
draw.rounded_rectangle((92, 59, 140, 103), 12, fill='#18362E')
center('<', 116, 81, 20)
draw.rounded_rectangle((78, 112, 388, 174), 10, fill='#12271F', outline='#8BAA94')
draw.text((90, 131), 'Hoy aprendí...', font=font(16), fill='#C2D5C9')
index, boxes = 0, []
for row_index, row in enumerate(rows):
    units = [weights.get(index + offset, 1) for offset in range(len(row))]
    unit = (width - 3 * (len(row) - 1)) / sum(units)
    x = (466 - width) / 2
    y = top + row_index * (height + 3) / len(rows)
    for key, weight in zip(row, units):
        key_width = weight * unit
        bottom = y + (height - 3 * (len(rows) - 1)) / len(rows)
        box = (x, y, x + key_width, bottom)
        assert all((px - 233)**2 + (py - 233)**2 < 233**2 for px in (box[0], box[2]) for py in (box[1], box[3])), 'Key extends outside the round display'
        draw.rounded_rectangle(box, 8, fill='#234538')
        center(key, x + key_width / 2, (y + bottom) / 2)
        boxes.append({'key': key, 'bounds': box})
        x += key_width + 3
        index += 1
center('Pulsa Enviar para continuar', 233, 419, 14)
image.save(output / 'compose.png')
(output / 'report.json').write_text(json.dumps({'source': 'C keyboard map and bounds', 'physicalScreenshot': False,
    'fontApproximation': 'Host TTF, not device bitmap rasterization', 'keys': len(boxes),
    'allKeysInsideCircle': True, 'minimumKeyHeight': (height - 3 * (len(rows) - 1)) / len(rows),
    'bounds': boxes}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'keys': len(boxes), 'allKeysInsideCircle': True, 'output': str(output / 'compose.png')}))
