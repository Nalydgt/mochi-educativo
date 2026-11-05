#include "mochi_fonts.h"
LV_FONT_DECLARE(mochi_latin_14);
LV_FONT_DECLARE(mochi_latin_16);
LV_FONT_DECLARE(mochi_latin_20);
lv_font_t mochi_font_14,mochi_font_16,mochi_font_20;

void mochi_fonts_init(void)
{
    mochi_font_14=lv_font_montserrat_14;mochi_font_14.fallback=&mochi_latin_14;
    mochi_font_16=lv_font_montserrat_16;mochi_font_16.fallback=&mochi_latin_16;
    mochi_font_20=lv_font_montserrat_20;mochi_font_20.fallback=&mochi_latin_20;
}
unsigned mochi_fonts_missing(void)
{
    const uint32_t glyphs[]={0xC1,0xC9,0xCD,0xD3,0xDA,0xE1,0xE9,0xED,0xF3,0xFA,
        0xD1,0xF1,0xDC,0xFC,0xA1,0xBF,0xB0,0xB7,0x2026,0x2212,0x2192};
    const lv_font_t *fonts[]={&mochi_font_14,&mochi_font_16,&mochi_font_20};
    unsigned missing=0;
    for(unsigned f=0;f<3;f++)for(unsigned g=0;g<sizeof(glyphs)/sizeof(glyphs[0]);g++){
        lv_font_glyph_dsc_t dsc;
        if(!lv_font_get_glyph_dsc(fonts[f],&dsc,glyphs[g],0)||dsc.is_placeholder)missing++;
    }
    return missing;
}
