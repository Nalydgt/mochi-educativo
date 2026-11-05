/* Native storybook scenes: apples in baskets, fish in ponds, toy cars in boxes.
 * One bounded draw surface, no bitmap frames or per-item allocation.
 * Scene identity is deterministic: zero-based downloaded step modulo three.
 * Collections through 48 objects are drawn in full. Larger totals use explicit
 * quantity labels instead of a misleading partial collection. */
#include "mochi_lesson_scene.h"
#include "mochi_fonts.h"
#include "src/draw/lv_draw_rect.h"
#include "src/draw/lv_draw_label.h"
#include "src/draw/lv_draw_triangle.h"
#include "src/draw/lv_draw_line.h"
#include "esp_timer.h"
#include <math.h>
#include <stdio.h>
#define WIDTH 338
#define HEIGHT 132
#define PI 3.14159265358979323846f
#define CREAM 0xF9EED3
#define GOLD 0xF4CD76
#define MINT 0x9BD3AE
#define LEAF 0x69AE8E
#define CORAL 0xF0907A
#define WATER 0x2C788F
static lv_obj_t *surface;
static mochi_lesson_scene_mode_t mode;
static unsigned groups,quantity,hint,progress,total,motion_mode;
static int64_t changed_at,frame_at;
static bool active,shown;
static uint16_t phase;
static unsigned draw_items,drawn_objects,drawn_groups;
static int clamp(int n,int low,int high){return n<low?low:n>high?high:n;}
static void rect(lv_layer_t *l,int x,int y,int w,int h,int radius,uint32_t color,lv_opa_t a,uint32_t border,int stroke){
    if(w<1||h<1||!a)return;
    lv_draw_rect_dsc_t d;lv_draw_rect_dsc_init(&d);d.bg_color=lv_color_hex(color);d.bg_opa=a;d.radius=radius;
    d.border_color=lv_color_hex(border);d.border_width=stroke;d.border_opa=stroke?a:0;
    lv_area_t area={.x1=x,.y1=y,.x2=x+w-1,.y2=y+h-1};lv_draw_rect(l,&d,&area);draw_items++;
}
static void text(lv_layer_t *l,const char *value,int x,int y,int w,const lv_font_t *font,uint32_t color,lv_opa_t a){
    lv_draw_label_dsc_t d;lv_draw_label_dsc_init(&d);d.text=value;d.text_local=true;d.font=font;
    d.align=LV_TEXT_ALIGN_CENTER;d.color=lv_color_hex(color);d.opa=a;
    lv_area_t area={.x1=x,.y1=y,.x2=x+w-1,.y2=y+24};lv_draw_label(l,&d,&area);draw_items++;
}
static void line(lv_layer_t *l,int x1,int y1,int x2,int y2,int width,uint32_t color,lv_opa_t a){
    lv_draw_line_dsc_t d;lv_draw_line_dsc_init(&d);d.p1=(lv_point_precise_t){x1,y1};d.p2=(lv_point_precise_t){x2,y2};
    d.width=width;d.color=lv_color_hex(color);d.opa=a;d.round_start=1;d.round_end=1;lv_draw_line(l,&d);draw_items++;
}
static void tri(lv_layer_t *l,int x1,int y1,int x2,int y2,int x3,int y3,uint32_t color,lv_opa_t a){
    lv_draw_triangle_dsc_t d;lv_draw_triangle_dsc_init(&d);d.p[0]=(lv_point_precise_t){x1,y1};
    d.p[1]=(lv_point_precise_t){x2,y2};d.p[2]=(lv_point_precise_t){x3,y3};
    d.color=lv_color_hex(color);d.opa=a;lv_draw_triangle(l,&d);draw_items++;
}
static void oval(lv_layer_t *l,int cx,int cy,int w,int h,uint32_t color,lv_opa_t a){
    /* A single native rounded primitive has no internal antialiased edges.
     * Triangle fans left visible radial seams on the physical AMOLED. */
    rect(l,cx-w/2,cy-h/2,w,h,LV_RADIUS_CIRCLE,color,a,0,0);
}
static void arch(lv_layer_t *l,int x,int y,int w,int h,int stroke,uint32_t color,lv_opa_t a){
    int px=x,py=y+h;
    for(unsigned i=1;i<=12;i++){float t=PI+i*PI/12;int nx=x+w/2+(int)lroundf(cosf(t)*w*.5f),ny=y+h+(int)lroundf(sinf(t)*h);
        line(l,px,py,nx,ny,stroke,color,a);px=nx;py=ny;}
}
static float reveal(unsigned index,unsigned count){
    if(motion_mode==2)return 1;
    float duration=motion_mode==1?300.f:620.f,time=phase*20.f-index*(count<=4?85.f:35.f),p=time/duration;
    if(p<=0)return 0;
    if(p>=1)return 1;
    float remain=1-p;return 1-remain*remain*remain*remain;
}
static void flower(lv_layer_t *l,int x,int y,int size,lv_opa_t a){
    line(l,x,y,x,y+size*2,1,LEAF,a);
    rect(l,x-size,y-2,size*2+1,5,3,CORAL,a,0,0);rect(l,x-2,y-size,5,size*2+1,3,CORAL,a,0,0);
    rect(l,x-2,y-2,5,5,3,GOLD,a,0,0);
}
static void apple(lv_layer_t *l,int x,int y,int size,lv_opa_t a){
    /* Two lobes, stem, leaf and body; no item is represented by a plain dot. */
    line(l,x,y+size/4,x+1,y+1,size>21?2:1,0xB98E64,a);
    tri(l,x+1,y+size/6,x+size/3,y,x+size/4,y+size/4,LEAF,a);
    rect(l,x-size/2,y+size/4,size,size*7/10,size/3,CORAL,a,0,0);
    rect(l,x-size/2,y+size/5,size*3/5,size/2,size/3,0xF7AA8A,a,0,0);
    rect(l,x-size/12,y+size/5,size*3/5,size/2,size/3,CORAL,a,0,0);
    if(size>=18)line(l,x-size/4,y+size*2/5,x-size/4,y+size*3/5,2,0xFFD2AF,a);
}
static void fish(lv_layer_t *l,int x,int y,int size,lv_opa_t a){
    int h=size*3/5;
    tri(l,x-size/2,y+1,x-size/2,y+h-1,x-size/5,y+h/2,0xF5B66D,a);
    rect(l,x-size/3,y,size*5/6,h,h/2,GOLD,a,0,0);
    tri(l,x-size/10,y+1,x+size/8,y-h/5,x+size/4,y+1,0xF5B66D,a);
    rect(l,x+size/4,y+h/4,size>=20?3:2,size>=20?3:2,2,0x183D47,a,0,0);
    if(size>=20)line(l,x-size/12,y+h/2,x+size/14,y+h*3/4,2,0xDE8D5F,a);
}
static void car(lv_layer_t *l,int x,int y,int size,lv_opa_t a){
    int wheel=size>25?7:size>17?5:3;
    rect(l,x-size/2+size/5,y,size*3/5,size/3,size/6,0xA4DAD6,a,0,0);
    rect(l,x-size/2,y+size/4,size,size/3,size/8,0x77B9CA,a,0,0);
    if(size>=16){rect(l,x-size/4,y+2,size/5,size/5,2,0xDDF2EB,a,0,0);rect(l,x+1,y+2,size/5,size/5,2,0xDDF2EB,a,0,0);}
    rect(l,x-size/3-wheel/2,y+size/2,wheel,wheel,wheel/2,0x253D4E,a,0,0);
    rect(l,x+size/3-wheel/2,y+size/2,wheel,wheel,wheel/2,0x253D4E,a,0,0);
}
static void object(lv_layer_t *l,unsigned theme,int x,int y,int size,lv_opa_t a){
    if(theme==0)apple(l,x,y,size,a);else if(theme==1)fish(l,x,y,size,a);else car(l,x,y,size,a);
    drawn_objects++;
}
static void draw_groups(lv_layer_t *l,int ox,int oy,int height){
    unsigned columns=groups<=3?groups:groups==4?2:groups<=6?3:4;
    unsigned rows=(groups+columns-1)/columns,theme=progress%3;
    int gap=groups<=3?12:8,cw=(WIDTH-(columns-1)*gap)/columns;if(cw>164)cw=164;
    int ch=(height-4-(rows-1)*4)/rows,left=(WIDTH-(columns*cw+(columns-1)*gap))/2;
    bool all_objects=groups*quantity<=48;unsigned highlighted=phase/33%groups;
    for(unsigned group=0;group<groups;group++){
        float p=reveal(group,groups);if(p<=0)continue;
        lv_opa_t a=(lv_opa_t)(p*255);
        int x=ox+left+(group%columns)*(cw+gap),y=oy+2+(group/columns)*(ch+4);
        if(motion_mode==0)y+=(int)((1-p)*8);
        bool focus=hint&&(motion_mode==2||highlighted==group);
        int label_h=rows==3?16:20,art_h=ch-label_h,inner_w=cw-14,inner_h=art_h-13;
        /* Choose the largest complete, non-overlapping collection. A fixed
         * three-column rule made five apples too small in a short basket. */
        unsigned per_row=quantity;
        int size=0,row_gap=2;
        float aspect=theme==0?1.f:theme==1?.65f:.80f;
        for(unsigned candidate=1;candidate<=quantity;candidate++){
            unsigned nr=(quantity+candidate-1)/candidate;
            int available_w=(inner_w-((int)candidate-1)*3)/(int)candidate;
            int available_h=(int)((inner_h-((int)nr-1)*row_gap)/(nr*aspect));
            int trial=clamp(available_w<available_h?available_w:available_h,0,34);
            while(trial>0 && (int)(nr*(int)ceilf(trial*aspect)+(nr-1)*row_gap)>inner_h)trial--;
            if(trial>size){size=trial;per_row=candidate;}
        }
        unsigned item_rows=(quantity+per_row-1)/per_row;
        if(size<1)size=1;
        int icon_h=(int)ceilf(size*aspect);
        int collection_h=item_rows*icon_h+(item_rows-1)*row_gap,item_y=y+3+(inner_h-collection_h)/2;
        if(item_y<y+2)item_y=y+2;
        if(theme==0){
            int back_y=y+art_h/3;
            arch(l,x+cw/5,y+1,cw*3/5,art_h*2/3,2,focus?GOLD:0x987455,a);
            rect(l,x+7,back_y,cw-14,art_h-(back_y-y)-3,5,0x5D4633,a,0,0);
        }else if(theme==1){
            oval(l,x+cw/2,y+art_h/2,cw-4,art_h,focus?GOLD:0x6EA6A0,a);
            oval(l,x+cw/2,y+art_h/2,cw-9,art_h-5,WATER,a);
            line(l,x+cw/6,y+art_h-6,x+cw/3,y+art_h-6,1,0x8ECACB,a);
        }else{
            rect(l,x+5,y+art_h/3,cw-10,art_h*2/3-2,4,0x715744,a,0,0);
            tri(l,x+5,y+art_h/3,x+cw/3,y+art_h/3-7,x+cw/3,y+art_h/3+6,0xC39A70,a);
            tri(l,x+cw-5,y+art_h/3,x+cw*2/3,y+art_h/3-7,x+cw*2/3,y+art_h/3+6,0xC39A70,a);
        }
        if(all_objects){
            for(unsigned item=0;item<quantity;item++){
                unsigned row=item/per_row,col=item%per_row,in_row=quantity-row*per_row;if(in_row>per_row)in_row=per_row;
                int row_width=in_row*size+(in_row-1)*3,ix=x+(cw-row_width)/2+col*(size+3)+size/2;
                int iy=item_y+row*(icon_h+row_gap);object(l,theme,ix,iy,size,a);
            }
        }else{
            char value[8];snprintf(value,sizeof(value),"%u",quantity);
            text(l,value,x,y+(art_h-22)/2,cw,&mochi_font_20,CREAM,a);
        }
        if(theme!=1){
            int base=y+art_h-9;rect(l,x+5,base,cw-10,9,3,focus?GOLD:0xBB9268,a,0,0);
            if(cw>70){line(l,x+cw/3,base+2,x+cw/3,base+6,1,0x6F513B,a);line(l,x+cw*2/3,base+2,x+cw*2/3,base+6,1,0x6F513B,a);}
        }
        char value[12];snprintf(value,sizeof(value),"%u",quantity);
        text(l,value,x,y+art_h+1,cw,rows==1?&mochi_font_16:&mochi_font_14,focus?GOLD:CREAM,a);drawn_groups++;
    }
}
static void house(lv_layer_t *l,int x,int y,int size,unsigned theme,bool current,bool done,lv_opa_t a){
    int w=size,h=size*3/4;uint32_t roof=theme==0?CORAL:theme==1?0x80BFCB:GOLD;
    rect(l,x-w/2+4,y+h/3,w-8,h*2/3,5,theme==1?0xB4D4D1:0xEAD6A7,a,0,0);
    rect(l,x+w/5,y+h/7,5,h/3,2,0xCEAC83,a,0,0);
    tri(l,x,y,x-w/2,y+h/2,x+w/2,y+h/2,roof,a);
    line(l,x-w/2,y+h/2,x,y,2,roof,a);line(l,x,y,x+w/2,y+h/2,2,roof,a);
    rect(l,x-5,y+h*2/3,10,h/3,4,current?0x3E7969:0x736A55,a,0,0);
    rect(l,x-w/4-3,y+h/2+3,6,7,2,current?GOLD:0x8AAEA5,a,0,0);
    rect(l,x+w/4-3,y+h/2+3,6,7,2,current?GOLD:0x8AAEA5,a,0,0);
    if(done){rect(l,x-7,y+h+3,14,14,7,LEAF,a,0,0);line(l,x-3,y+h+10,x,y+h+13,2,CREAM,a);line(l,x,y+h+13,x+5,y+h+7,2,CREAM,a);}
    else if(current)tri(l,x-4,y+h+6,x+4,y+h+6,x,y+h+12,GOLD,a);
}
static void garden(lv_layer_t *l,int ox,int oy,int width,int height,unsigned done,unsigned count,bool complete){
    count=clamp(count,1,5);done=clamp(done,0,count);float scale=height<95?.70f:1.f;
    int ground=oy+height-18,top=oy+(height<95?2:12);
    oval(l,ox+width/2,ground+5,width-6,33,0x193D32,255);oval(l,ox+width/2-59,ground+5,width*2/3,24,0x254E38,255);
    int prior_x=ox+20,prior_y=ground+8;
    for(unsigned i=0;i<count;i++){
        int x=ox+33+(width-66)*(i+1)/(count+1);if(count==1)x=ox+width/2;
        int y=top+(i%2?0:17*scale),size=(int)((count<=3?58:43)*scale),door_y=y+size*3/4;
        /* Only real downloaded steps become houses on this little trail. */
        for(unsigned n=1;n<=4;n++){float u=n/4.f;int sx=prior_x+(int)((x-prior_x)*u),sy=prior_y+(int)((door_y+12-prior_y)*u);
            oval(l,sx,sy,9,5,i<done?0xC7B77D:0x6F8270,255);}
        prior_x=x;prior_y=door_y+12;house(l,x,y,size,i%3,!complete&&i==done,i<done,255);
        if(height>=95){char value[8];snprintf(value,sizeof(value),"%u",i+1);text(l,value,x-16,y+size*3/4+20,32,&mochi_font_14,i==done?GOLD:0xAEC6AC,255);}
    }
    flower(l,ox+21,ground-8,4,220);flower(l,ox+width-23,ground-11,3,220);
    if(height>=95){
        rect(l,ox+17,top+9,4,24,2,0x8C7757,255,0,0);oval(l,ox+19,top+3,26,26,LEAF,255);
        rect(l,ox+width-23,top+20,4,25,2,0x8C7757,255,0,0);oval(l,ox+width-21,top+11,28,29,0x417D62,255);
    }
}
static void draw_hub(lv_layer_t *l,int x,int y,int height,bool complete){
    float p=reveal(0,1);int lift=motion_mode==0?(int)((1-p)*6):0;
    garden(l,x,y+lift,WIDTH,height-lift,complete?total:progress,total,complete);
    if(complete)for(unsigned i=0;i<5;i++){int cx=x+43+i*62,cy=y+9+(i%2)*9;float q=reveal(i+1,6);if(q<=0)continue;
        int r=3+(int)(q*2);line(l,cx-r,cy,cx+r,cy,2,GOLD,q*255);line(l,cx,cy-r,cx,cy+r,2,GOLD,q*255);}
}
static void draw_voice(lv_layer_t *l,int x,int y,int height){
    /* A voice-mode light, not a fabricated microphone reading or diagnosis. */
    int center=x+WIDTH/2,base=y+height-20;oval(l,center,base+6,188,24,0x1B3C32,255);
    house(l,center,base-65,72,1,true,false,255);
    for(unsigned i=0;i<3;i++){float change=motion_mode==2?.5f:.5f+.4f*sinf(phase*.13f-i*.8f);int h=active?10+(int)(change*22):8;
        rect(l,center-16+i*12,base-16-h,7,h,4,i%2?GOLD:MINT,255,0,0);}
    flower(l,center-65,base-6,4,255);flower(l,center+65,base-6,3,255);
}
static void draw(lv_event_t *event){
    lv_layer_t *l=lv_event_get_layer(event);lv_area_t c;lv_obj_get_coords(surface,&c);
    int height=lv_obj_get_height(surface);draw_items=drawn_objects=drawn_groups=0;
    if(mode==MOCHI_SCENE_HUB)draw_hub(l,c.x1,c.y1,height,false);
    else if(mode==MOCHI_SCENE_COMPLETE)draw_hub(l,c.x1,c.y1,height,true);
    else if(mode==MOCHI_SCENE_VOICE)draw_voice(l,c.x1,c.y1,height);
    else if(groups&&quantity)draw_groups(l,c.x1,c.y1,height);
}
static void draw_launcher(lv_event_t *event){
    lv_obj_t *button=lv_event_get_target(event);lv_area_t c;lv_obj_get_coords(button,&c);lv_layer_t *l=lv_event_get_layer(event);
    oval(l,c.x1+43,c.y1+57,70,16,0x345D45,255);house(l,c.x1+43,c.y1+9,46,0,true,false,255);flower(l,c.x1+14,c.y1+48,3,255);
}
void mochi_lesson_scene_decorate_launcher(lv_obj_t *button){lv_obj_add_event_cb(button,draw_launcher,LV_EVENT_DRAW_MAIN,NULL);}
lv_obj_t *mochi_lesson_scene_create(lv_obj_t *parent,int y){
    surface=lv_obj_create(parent);lv_obj_remove_style_all(surface);lv_obj_set_size(surface,WIDTH,HEIGHT);
    lv_obj_align(surface,LV_ALIGN_TOP_MID,0,y);lv_obj_remove_flag(surface,LV_OBJ_FLAG_CLICKABLE|LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_event_cb(surface,draw,LV_EVENT_DRAW_MAIN,NULL);changed_at=esp_timer_get_time();return surface;
}
void mochi_lesson_scene_set(mochi_lesson_scene_mode_t next,unsigned a,unsigned b,unsigned help,unsigned done,unsigned count,bool live){
    bool changed=mode!=next||groups!=a||quantity!=b||hint!=help||progress!=done||total!=count||active!=live;
    mode=next;groups=clamp(a,0,12);quantity=clamp(b,0,12);hint=help;progress=done;total=count;active=live;
    if(changed){changed_at=esp_timer_get_time();phase=0;}
    if(surface&&changed)lv_obj_invalidate(surface);
}
void mochi_lesson_scene_tick(int64_t now,unsigned motion,bool visible){
    if(!surface)return;
    bool motion_changed=motion_mode!=motion;shown=visible;motion_mode=motion;if(!visible)return;
    unsigned next=clamp((now-changed_at)/20000,0,60000);
    bool animate=motion<2&&((mode==MOCHI_SCENE_VOICE&&active)||now-changed_at<1800000||
                  (mode==MOCHI_SCENE_GROUPS&&hint&&now-changed_at<9000000));
    if(motion_changed||(phase!=next&&(animate||frame_at<changed_at))){phase=next;frame_at=now;lv_obj_invalidate(surface);}
}
void mochi_lesson_scene_diagnose(void){
    static const char *const themes[]={"apples","fish","cars"};
    printf("@mochi_lesson_scene ready=%d visible=%d mode=%u groups=%u quantity=%u motion=%u draw_items=%u bitmap_frames=0 theme=%s objects=%u visible_groups=%u labelled=%d\n",
        surface!=NULL,shown,(unsigned)mode,groups,quantity,motion_mode,draw_items,themes[progress%3],drawn_objects,drawn_groups,groups*quantity>48);
}
