// Add Latin glyphs without duplicating LVGL's ASCII and symbol fonts.
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
for(const size of [14,16,20])execFileSync(process.execPath,[
  path.join(root,'tools/fonts/node_modules/lv_font_conv/lv_font_conv.js'),
  '--no-compress','--no-prefilter','--bpp','4','--size',String(size),
  '--font',path.join(root,'tools/fonts/Montserrat-Medium.ttf'),
  '-r','0xA0-0x17F,0x2010-0x2027,0x20AC,0x2190-0x2193,0x2212',
  '--format','lvgl','--lv-include','lvgl.h','--lv-font-name',`mochi_latin_${size}`,
  '-o',path.join(root,`firmware/main/mochi_latin_${size}.c`)
],{stdio:'inherit'});
