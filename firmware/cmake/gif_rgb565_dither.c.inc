/* Keep the original 8-bit palette until the last RGB565 conversion. Ordered
 * dithering avoids coloured contour bands on Mochi's soft grey shading. */
static inline uint16_t mochi_gif_rgb565(const uint8_t *rgb, int x, int y)
{
    static const uint8_t bayer[4][4]={{0,8,2,10},{12,4,14,6},{3,11,1,9},{15,7,13,5}};
    unsigned threshold=bayer[y&3][x&3]*16+8;
    unsigned r=(rgb[0]*31+threshold)/255;
    unsigned g=(rgb[1]*63+threshold)/255;
    unsigned b=(rgb[2]*31+threshold)/255;
    return (uint16_t)((r<<11)|(g<<5)|b);
}

static inline void mochi_gif_blend_rgb565(GIFDRAW *p, lv_draw_buf_t *buffer)
{
    int y=p->iY+p->y;
    uint16_t *dst=(uint16_t *)(buffer->data+y*buffer->header.stride)+p->iX;
    for (int column=0;column<p->iWidth;column++) {
        unsigned pixel=p->pPixels[column];
        if (p->ucHasTransparency && pixel==p->ucTransparent) {
            if (p->ucDisposalMethod!=2) continue;
            pixel=p->ucBackground;
        }
        dst[column]=mochi_gif_rgb565(p->pPalette24+pixel*3,p->iX+column,y);
    }
}
