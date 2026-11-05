/* Host adapter: the production C is included and executed unchanged. Only LVGL
 * draw descriptors are emitted as SVG. Font rasterization is the host's, not
 * the device's Montserrat bitmaps; this is a geometry/count preview. */
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include "stub/lvgl.h"
lv_font_t mochi_font_14={14},mochi_font_16={16},mochi_font_20={20};
static lv_obj_t object_stub;
lv_obj_t *lv_obj_create(lv_obj_t *parent){(void)parent;return &object_stub;}
static void escaped(const char *s){for(;*s;s++){if(*s=='&')fputs("&amp;",stdout);else if(*s=='<')fputs("&lt;",stdout);else if(*s=='>')fputs("&gt;",stdout);else putchar(*s);}}
void lv_draw_rect(lv_layer_t *l,const lv_draw_rect_dsc_t *d,const lv_area_t *a){
    (void)l;int w=a->x2-a->x1+1,h=a->y2-a->y1+1,r=d->radius;if(r>w/2)r=w/2;if(r>h/2)r=h/2;
    printf("<rect x='%d' y='%d' width='%d' height='%d' rx='%d' fill='#%06x' fill-opacity='%.4f' stroke='#%06x' stroke-width='%d' stroke-opacity='%.4f'/>\n",a->x1,a->y1,w,h,r,d->bg_color,d->bg_opa/255.,d->border_color,d->border_width,d->border_opa/255.);
}
void lv_draw_label(lv_layer_t *l,const lv_draw_label_dsc_t *d,const lv_area_t *a){
    (void)l;printf("<text x='%.1f' y='%d' text-anchor='middle' font-family='Montserrat,sans-serif' font-size='%d' fill='#%06x' opacity='%.4f'>",(a->x1+a->x2+1)/2.,a->y1+d->font->size,d->font->size,d->color,d->opa/255.);escaped(d->text);puts("</text>");
}
void lv_draw_line(lv_layer_t *l,const lv_draw_line_dsc_t *d){(void)l;printf("<line x1='%d' y1='%d' x2='%d' y2='%d' stroke='#%06x' stroke-width='%d' stroke-linecap='round' opacity='%.4f'/>\n",d->p1.x,d->p1.y,d->p2.x,d->p2.y,d->color,d->width,d->opa/255.);}
void lv_draw_triangle(lv_layer_t *l,const lv_draw_triangle_dsc_t *d){(void)l;printf("<path d='M%d %d L%d %d L%d %d Z' fill='#%06x' opacity='%.4f'/>\n",d->p[0].x,d->p[0].y,d->p[1].x,d->p[1].y,d->p[2].x,d->p[2].y,d->color,d->opa/255.);}
#include "../../firmware/main/mochi_lesson_scene.c"
static void ui_button(const char *value,int x,int y,int w,int h,uint32_t fill,uint32_t ink){
    rect(NULL,x,y,w,h,12,fill,255,0,0);
    text(NULL,value,x,y+(h-20)/2,w,&mochi_font_16,ink,255);
}
static void ui_header(void){
    rect(NULL,185,47,31,16,2,0,0,0xB5B7C3,2);rect(NULL,189,51,23,8,1,0xB5B7C3,255,0,0);
    rect(NULL,218,52,3,6,1,0xB5B7C3,255,0,0);text(NULL,"100%",230,45,56,&mochi_font_14,0xD8E0DA,255);
    rect(NULL,313,60,48,48,20,0x232632,255,0,0);
    for(unsigned i=0;i<8;i++){float a=i*PI/4;line(NULL,337+(int)(cosf(a)*6),84+(int)(sinf(a)*6),337+(int)(cosf(a)*9),84+(int)(sinf(a)*9),3,0xECECF3,255);}
    rect(NULL,333,80,9,9,4,0xECECF3,255,0,0);rect(NULL,335,82,5,5,3,0x232632,255,0,0);
    ui_button("Misión",82,74,96,44,0x142B24,0xEDF5EB);
    ui_button("Hablar",209,74,96,44,0x142B24,0xEDF5EB);
}
static void ui_text_scroll(const char *value,int y,int height){
    printf("<defs><clipPath id='reading'><rect x='81' y='%d' width='300' height='%d'/></clipPath></defs><g clip-path='url(#reading)'>\n",y,height);
    char row[80];unsigned used=0,lines=0;const char *p=value;
    while(*p){const char *start=p;while(*p&&*p!=' ')p++;unsigned length=(unsigned)(p-start);
        if(used+length+1>37){row[used]=0;text(NULL,row,83,y+lines*21,294,&mochi_font_16,0xE4EBE3,255);used=0;lines++;}
        if(used)row[used++]=' ';for(unsigned i=0;i<length&&used<78;i++)row[used++]=start[i];
        if(*p)p++;
    }
    if(used){row[used]=0;text(NULL,row,83,y+lines*21,294,&mochi_font_16,0xE4EBE3,255);}
    puts("</g>");rect(NULL,383,y,3,height,2,0x20352C,255,0,0);rect(NULL,383,y,3,height/2,2,0x83A38F,255,0,0);
}
int main(int argc,char **argv){
    if(argc<2)return 2;
    const char *name=argv[1];unsigned a=argc>2?atoi(argv[2]):3,b=argc>3?atoi(argv[3]):3,step=argc>4?atoi(argv[4]):0;
    unsigned help=argc>5?atoi(argv[5]):0;
    mochi_lesson_scene_create(NULL,187);motion_mode=2;phase=100;progress=step;total=argc>6?atoi(argv[6]):3;groups=a;quantity=b;hint=help;active=true;
    if(!strcmp(name,"verify")){
        FILE *sink=freopen("NUL","w",stdout);(void)sink;unsigned cases=0,errors=0;
        mode=MOCHI_SCENE_GROUPS;lv_event_t event={surface};
        for(unsigned t=0;t<3;t++)for(unsigned x=1;x<=12;x++)for(unsigned y=1;y<=12;y++){
            progress=t;groups=x;quantity=y;draw(&event);cases++;
            unsigned expected=x*y<=48?x*y:0;
            if(drawn_objects!=expected||drawn_groups!=x){errors++;fprintf(stderr,"FAIL t=%u a=%u b=%u objects=%u groups=%u\n",t,x,y,drawn_objects,drawn_groups);}
        }
        fprintf(stderr,"{\"exhaustiveCases\":%u,\"errors\":%u,\"objectCountExactThrough48\":true,\"largerTotalsLabelOnly\":true}\n",cases,errors);return errors?1:0;
    }
    mode=!strcmp(name,"hub")?MOCHI_SCENE_HUB:!strcmp(name,"complete")?MOCHI_SCENE_COMPLETE:!strcmp(name,"voice")?MOCHI_SCENE_VOICE:MOCHI_SCENE_GROUPS;
    bool intro=!strcmp(name,"hub-compact"),reading=!strcmp(name,"help"),launcher=!strcmp(name,"launcher");
    if(intro){mode=MOCHI_SCENE_HUB;surface->h=76;}
    puts("<svg xmlns='http://www.w3.org/2000/svg' width='466' height='466' viewBox='0 0 466 466'><title>Host geometry preview; illustrative UI controls and header, not installed firmware capture</title><defs><clipPath id='round'><circle cx='233' cy='233' r='233'/></clipPath><clipPath id='scene'><rect x='64' y='187' width='338' height='132'/></clipPath></defs><g clip-path='url(#round)'><rect width='466' height='466' fill='#000000'/>");
    if(launcher){
        lv_obj_t tile={94,330,278,76};lv_event_t e={&tile};
        rect(NULL,94,330,278,76,22,0x173B2E,255,0x6CA888,1);draw_launcher(&e);
        text(NULL,"Nuestro jardín",182,348,171,&mochi_font_16,0xF9EED3,255);
        text(NULL,"Tu misión está aquí",182,372,171,&mochi_font_14,0xBDD6BF,255);
    }else{
        ui_header();
        char title[100];
        const char *containers[]={"cestas","estanques","cajas"},*items[]={"manzanas","peces","coches"};
        snprintf(title,sizeof(title),"%u %s con %u %s",a,containers[step%3],b,items[step%3]);
        const char *question=mode==MOCHI_SCENE_HUB?"El jardín de Mochi":mode==MOCHI_SCENE_COMPLETE?"¡Lo hicimos juntos!":mode==MOCHI_SCENE_VOICE?"Te escucho":title;
        text(NULL,question,74,147,318,&mochi_font_20,0xEDF5EB,255);
        if(reading){
            ui_text_scroll("Hay 3 grupos. Cada uno tiene 3 objetos. Cuenta por grupos.",187,132);
            ui_button("Volver al reto",123,334,220,48,GOLD,0x193B32);
        }else{
            puts("<g clip-path='url(#scene)'>");lv_event_t event={surface};draw(&event);puts("</g>");
            if(intro){
                ui_text_scroll("Enséñame cuántos objetos hay en estos grupos. Podemos contar juntos si lo necesitas.",274,52);
                ui_button("Empezar",123,334,220,48,GOLD,0x193B32);
            }else if(mode==MOCHI_SCENE_GROUPS){
                for(unsigned i=0;i<3;i++){unsigned colors[]={0xEDCAA1,0xADD8C2,0xACD2DF};rect(NULL,106+i*88,334,78,48,12,colors[i],255,0,0);char s[8];snprintf(s,sizeof(s),"%u",a*b+(i?i:0));text(NULL,s,106+i*88,347,78,&mochi_font_20,0x193B32,255);}
            }else ui_button("Empezar",123,334,220,48,GOLD,0x193B32);
        }
        ui_button("Pista",128,394,100,44,0x18362E,0xEDF5EB);
        ui_button("Descansar",238,394,100,44,0x18362E,0xEDF5EB);
    }
    puts("</g></svg>");
    fprintf(stderr,"{\"scene\":\"%s\",\"a\":%u,\"b\":%u,\"step\":%u,\"objects\":%u,\"groups\":%u,\"drawItems\":%u}\n",name,a,b,step,drawn_objects,drawn_groups,draw_items);return 0;
}
