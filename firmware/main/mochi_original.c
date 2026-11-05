/* MOCHI Bun renderer, 466 physical pixels.
 * Body: authored adaptation of the OneWorks Bun source preset, exported by the
 * official 1.0.0-rc.9 renderer. See assets/mochi-original/NOTICE.md and MIT text.
 * Face, clothing and motion below are a native hardware adaptation; they do not
 * import Coucou geometry, motion, image layers or sprite/GIF data.
 * Persisted appearance indices and the existing animation/console API remain
 * compatible. The original renderer remains in the source tree as an archive.
 */
#include "mochi_animation.h"
#include "mochi_appearance.h"
#include "mochi_audio.h"
#include "mochi_runtime.h"
#include "esp_lv_adapter.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <dirent.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define PI 3.14159265358979323846f
#define INK 0x262635
#define ROSE 0xF2A0B7
#define TEAL 0x69C3B0
#define GOLD 0xF2CA78
#define CORAL 0xEC8E92
#define CLAMP(v,a,b) fminf((b),fmaxf((a),(v)))

typedef struct { const char *id; int x,y; lv_image_dsc_t image; } original_asset_t;
#include "mochi_original_index.inc"
typedef struct { const char *id,*label,*group; unsigned duration_ms; bool loop; } clip_t;
static const clip_t clips[] = {
    {"idle","En calma","state",6000,true},
    {"working","Trabajando","state",4000,true},
    {"thinking","Pensando","state",4000,true},
    {"searching","Buscando","state",4000,true},
    {"approval","Pidiendo permiso","state",4000,true},
    {"question","Curiosidad","state",4000,true},
    {"error","Necesito ayuda","state",4000,false},
    {"finished","Celebración","state",4000,false},
    {"ratelimit","Necesito una pausa","state",4000,true},
    {"sleeping","Durmiendo","state",6000,true},
    {"dizzy","Mareo","state",3000,false},
    {"love","Cariño","emote",2800,false},
    {"surprised","Sorpresa","emote",2800,false},
    {"proud","Orgullo","emote",2800,false},
    {"wink","Guiño","emote",2800,false},
    {"yawn","Bostezo","emote",2800,false},
    {"happy","Alegría","emote",2800,false},
    {"annoyed","Travieso","emote",2800,false},
    {"greet","Saludo","gesture",2600,false},
    {"blink","Parpadeo","gesture",1000,false},
    {"look","Mirar alrededor","gesture",4800,false},
    {"squash","Rebote elástico","gesture",1500,false},
    {"slap","Golpecito y protesta","gesture",2200,false},
    {"roll","Vuelta completa","gesture",2200,false},
    {"mailbox","Carta para ti","gesture",4600,false},
    {"gulp","Pequeño bocado","gesture",3000,false},
    {"dance","Baile","gesture",6400,true},
    {"outfit_partyHat","Gorro de fiesta","outfit",3600,false},
    {"outfit_beanie","Gorro de lana","outfit",3600,false},
    {"outfit_crown","Corona","outfit",3600,false},
    {"outfit_sunglasses","Gafas de sol","outfit",3600,false},
    {"outfit_roundGlasses","Gafas redondas","outfit",3600,false},
    {"outfit_bow","Lazo","outfit",3600,false},
    {"outfit_scarf","Bufanda","outfit",3600,false},
    {"outfit_witchHat","Sombrero de bruja","outfit",3600,false},
    {"outfit_pumpkin","Calabaza","outfit",3600,false},
    {"outfit_santaHat","Gorro navideño","outfit",3600,false},
    {"outfit_bunnyEars","Orejas de conejo","outfit",3600,false},
    {"mini_love","Mini: cariño","mini",6800,true},
    {"mini_surprised","Mini: sorpresa","mini",6800,true},
    {"mini_proud","Mini: orgullo","mini",6800,true},
    {"mini_wink","Mini: guiño","mini",6800,true},
    {"mini_yawn","Mini: bostezo","mini",6800,true},
    {"mini_happy","Mini: alegría","mini",6800,true},
    {"mini_annoyed","Mini: travieso","mini",6800,true},
    {"update_hint","Actualización disponible","gesture",3000,false},
};
#define CLIP_COUNT (sizeof(clips)/sizeof(clips[0]))
typedef enum { EYE_OPEN,EYE_SMILE,EYE_CLOSED,EYE_HEART,EYE_STAR,EYE_SPIRAL } eye_t;
typedef struct {
    float x,y,sx,sy,roll,gaze_x,gaze_y,open_left,open_right,curve,mouth_open,blush;
    eye_t eye;
    bool brow,mini;
    unsigned effect;
} pose_t;
static pose_t pose;
static lv_obj_t *scene,*scene_home,*body,*face,*front,*back,*effects;
static lv_timer_t *animation_timer;
static const original_asset_t *body_asset;
static const clip_t *active;
static mochi_appearance_t appearance;
static mochi_state_t state=MOCHI_IDLE;
static bool created,wardrobe_view,preview,visible_last;
static int preview_outfit=-1;
static unsigned gallery_index,appearance_seen,frames,body_frames,render_us;
static unsigned frame_dt[64],frame_dt_count,frame_dt_index;
static unsigned mouth_pose,mouth_tick,mouth_sample_age,mouth_level,mouth_sequence;
static int64_t clip_started,preview_until,last_draw,last_interaction;
static float target_x,target_y,gaze_x,gaze_y;
static int applied_x=INT32_MIN,applied_y=INT32_MIN,applied_sx=-1,applied_sy=-1,applied_roll=-99999;
static uint32_t face_signature;
static int64_t draw_clock;
static lv_area_t scene_area;

static const clip_t *find_clip(const char *id) {
    if(!id)return NULL;
    for(unsigned i=0;i<CLIP_COUNT;i++)if(!strcmp(clips[i].id,id))return &clips[i];
    return NULL;
}
static const char *state_id(mochi_state_t next) {
    static const char *const ids[]={"idle","happy","love","surprised","error","sleeping","thinking","question","proud","wink","dizzy","working","idle","error","working","searching","approval","finished","ratelimit","yawn","annoyed","dance"};
    return (unsigned)next<MOCHI_STATE_COUNT?ids[next]:"idle";
}
static float view_scale(void){return wardrobe_view?.5f:1.f;}
static float view_x(float x){return wardrobe_view?168.f+(x-233.f)*.5f:x;}
static float view_y(float y){return wardrobe_view?114.f+(y-250.f)*.5f:y;}
static unsigned outfit(void){return preview_outfit>=0?(unsigned)preview_outfit:appearance.outfit;}
static void show(lv_obj_t *obj,bool value){if(value)lv_obj_remove_flag(obj,LV_OBJ_FLAG_HIDDEN);else lv_obj_add_flag(obj,LV_OBJ_FLAG_HIDDEN);}
static lv_point_precise_t point(float x,float y) {
    float xx=(x-233)*pose.sx,yy=(y-250)*pose.sy;
    float c=cosf(pose.roll),s=sinf(pose.roll);
    return (lv_point_precise_t){
        .x=(int32_t)lroundf(scene_area.x1+view_x(233+pose.x+xx*c-yy*s)),
        .y=(int32_t)lroundf(scene_area.y1+view_y(250+pose.y+xx*s+yy*c))};
}
static void line(lv_layer_t *layer,float x1,float y1,float x2,float y2,float width,uint32_t color,lv_opa_t opacity) {
    lv_draw_line_dsc_t d;lv_draw_line_dsc_init(&d);
    d.p1=point(x1,y1);d.p2=point(x2,y2);d.width=fmaxf(1,lroundf(width*view_scale()));
    d.color=lv_color_hex(color);d.opa=opacity;d.round_start=1;d.round_end=1;lv_draw_line(layer,&d);
}
static void triangle(lv_layer_t *layer,float x1,float y1,float x2,float y2,float x3,float y3,uint32_t color,lv_opa_t opacity) {
    lv_draw_triangle_dsc_t d;lv_draw_triangle_dsc_init(&d);
    d.p[0]=point(x1,y1);d.p[1]=point(x2,y2);d.p[2]=point(x3,y3);d.color=lv_color_hex(color);d.opa=opacity;
    lv_draw_triangle(layer,&d);
}
static void ellipse(lv_layer_t *layer,float x,float y,float width,float height,uint32_t color,lv_opa_t opacity) {
    /* Tessellated ellipse geometry keeps the native eyes elliptical through
     * expression and pose changes, rather than stretching a low-res sprite. */
    const unsigned n=20;
    float px=x+width*.5f,py=y;
    for(unsigned i=1;i<=n;i++){
        float a=(float)i*2*PI/n,nx=x+cosf(a)*width*.5f,ny=y+sinf(a)*height*.5f;
        triangle(layer,x,y,px,py,nx,ny,color,opacity);px=nx;py=ny;
    }
}
static void box(lv_layer_t *layer,float x,float y,float width,float height,float radius,uint32_t color) {
    /* Rotated clothing is composed of native filled geometry; rounded bands
     * use a central rectangle and four ellipse caps, all in the same pose. */
    float r=fminf(radius,fminf(width,height)*.5f);
    triangle(layer,x+r,y,x+width-r,y,x+width-r,y+height,color,255);
    triangle(layer,x+r,y,x+width-r,y+height,x+r,y+height,color,255);
    triangle(layer,x,y+r,x+width,y+r,x+width,y+height-r,color,255);
    triangle(layer,x,y+r,x+width,y+height-r,x,y+height-r,color,255);
    if(r>0){ellipse(layer,x+r,y+r,r*2,r*2,color,255);ellipse(layer,x+width-r,y+r,r*2,r*2,color,255);ellipse(layer,x+r,y+height-r,r*2,r*2,color,255);ellipse(layer,x+width-r,y+height-r,r*2,r*2,color,255);}
}
static void curve(lv_layer_t *layer,float cx,float cy,float width,float depth,float stroke,uint32_t color) {
    float px=cx-width*.5f,py=cy;
    for(unsigned i=1;i<=12;i++){
        float t=(float)i/12,nx=cx+(t-.5f)*width,ny=cy+4*t*(1-t)*depth;
        line(layer,px,py,nx,ny,stroke,color,255);px=nx;py=ny;
    }
}
static void heart(lv_layer_t *layer,float x,float y,float size,uint32_t color,lv_opa_t opacity) {
    /* Original native motif, not a borrowed icon or preset decal. */
    ellipse(layer,x-size*.22f,y-size*.15f,size*.55f,size*.55f,color,opacity);
    ellipse(layer,x+size*.22f,y-size*.15f,size*.55f,size*.55f,color,opacity);
    triangle(layer,x-size*.49f,y-size*.08f,x+size*.49f,y-size*.08f,x,y+size*.55f,color,opacity);
}
static void star(lv_layer_t *layer,float x,float y,float radius,uint32_t color,lv_opa_t opacity) {
    float px=x,py=y-radius;
    for(unsigned i=1;i<=10;i++){
        float a=-PI*.5f+i*PI/5,r=(i%2)?radius*.45f:radius,nx=x+cosf(a)*r,ny=y+sinf(a)*r;
        triangle(layer,x,y,px,py,nx,ny,color,opacity);px=nx;py=ny;
    }
}
static void ring(lv_layer_t *layer,float x,float y,float radius,float stroke,uint32_t color) {
    float px=x+radius,py=y;
    for(unsigned i=1;i<=32;i++){
        float a=i*PI/16,nx=x+cosf(a)*radius,ny=y+sinf(a)*radius;
        line(layer,px,py,nx,ny,stroke,color,255);px=nx;py=ny;
    }
}

static void draw_face(lv_event_t *event) {
    lv_layer_t *layer=lv_event_get_layer(event);lv_obj_get_coords(scene,&scene_area);
    for(unsigned i=0;i<2;i++){
        float x=(i?272.5f:194.5f)+pose.gaze_x*7,y=250.5f+pose.gaze_y*5;
        float open=i?pose.open_right:pose.open_left;
        ellipse(layer,i?288:178,268,29,8,ROSE,(lv_opa_t)(pose.blush*150));
        if(pose.eye==EYE_HEART){heart(layer,x,y,31,CORAL,255);continue;}
        if(pose.eye==EYE_STAR){star(layer,x,y,18,GOLD,255);continue;}
        if(pose.eye==EYE_SPIRAL){
            float px=x,py=y;
            for(unsigned n=1;n<48;n++){float a=n*.31f,rad=n*.3f,nx=x+cosf(a)*rad,ny=y+sinf(a)*rad;
                line(layer,px,py,nx,ny,3,INK,255);px=nx;py=ny;}continue;
        }
        if(pose.eye==EYE_CLOSED||pose.eye==EYE_SMILE||open<.18f){
            curve(layer,x,y,29,pose.eye==EYE_SMILE?-9:5,4,INK);
        } else {
            float w=31+(open-1)*3,h=27*open;
            ellipse(layer,x,y,w,h,INK,255);
            if(h>10)ellipse(layer,x-w*.20f,y-h*.18f,fminf(11,w*.36f),fminf(9,h*.34f),0xFFFFFF,255);
        }
        if(pose.brow){float direction=i?1:-1;line(layer,x-13,y-25-direction*4,x+13,y-25+direction*4,3,INK,255);}
    }
    float mx=233+pose.gaze_x*2,my=293.5f+pose.gaze_y*1.5f;
    if(pose.mouth_open>1){
        float h=pose.mouth_open,w=CLAMP(17+h*.32f,17,33);
        ellipse(layer,mx,my,w,h,INK,255);
        if(h>14)ellipse(layer,mx,my+h*.22f,w*.55f,h*.30f,0xEC9DAF,255);
    }else curve(layer,mx,my,39,pose.curve,4,INK);
}
static void draw_back(lv_event_t *event) {
    if(outfit()!=11)return;
    lv_layer_t *layer=lv_event_get_layer(event);lv_obj_get_coords(scene,&scene_area);
    box(layer,178,51,32,112,16,0xE9EDF7);box(layer,256,48,32,115,16,0xE9EDF7);
    box(layer,187,60,14,84,7,0xEAB0C3);box(layer,265,57,14,87,7,0xEAB0C3);
}
static void draw_front(lv_event_t *event) {
    unsigned look=outfit();if(!look)return;
    lv_layer_t *l=lv_event_get_layer(event);lv_obj_get_coords(scene,&scene_area);
    switch(look){
    case 1:
        triangle(l,232,52,189,143,276,143,CORAL,255);
        line(l,209,102,249,84,9,GOLD,255);line(l,197,130,264,103,9,TEAL,255);
        ellipse(l,232,53,21,21,TEAL,255);break;
    case 2:
        box(l,151,110,164,48,24,0x3E817A);box(l,146,142,174,19,8,TEAL);
        for(unsigned i=0;i<9;i++)line(l,161+i*18,148,161+i*18,155,2,0x3E817A,180);
        ellipse(l,233,99,29,29,TEAL,255);break;
    case 3:
        for(unsigned i=0;i<5;i++)triangle(l,157+i*33,128,165+i*33,91+(i%2)*9,189+i*33,128,GOLD,255);
        box(l,156,123,166,26,6,GOLD);ellipse(l,233,135,12,12,CORAL,255);break;
    case 4:
        box(l,164,233,61,35,12,INK);box(l,242,233,61,35,12,INK);
        line(l,222,244,245,244,5,INK,255);line(l,155,235,165,241,4,INK,255);line(l,302,241,312,235,4,INK,255);
        line(l,176,242,195,242,3,0xA0C7D9,190);line(l,254,242,273,242,3,0xA0C7D9,190);break;
    case 5:
        ring(l,194.5f,250.5f,27,3,0x68617D);ring(l,272.5f,250.5f,27,3,0x68617D);
        curve(l,233.5f,246,24,-5,3,0x68617D);line(l,158,241,168,246,3,0x68617D,255);line(l,299,246,310,241,3,0x68617D,255);break;
    case 6:
        triangle(l,290,144,264,127,264,162,CORAL,255);triangle(l,295,144,322,125,322,164,CORAL,255);
        ellipse(l,292,144,18,19,0xD77289,255);break;
    case 7:
        box(l,113,331,241,28,14,TEAL);box(l,283,347,31,53,9,0x3E817A);
        for(unsigned i=0;i<3;i++)line(l,289+i*8,391,289+i*8,400,3,TEAL,255);
        break;
    case 8:
        triangle(l,246,41,160,139,300,139,0x665484,255);box(l,127,132,211,22,11,0x4F4368);
        line(l,179,125,283,125,12,CORAL,255);box(l,224,116,21,18,3,GOLD);break;
    case 9:
        box(l,118,321,230,47,23,0xE6A063);
        for(unsigned i=0;i<5;i++)curve(l,149+i*42,328,13,26,2,0xBC7949);
        box(l,224,108,15,26,5,0x529D80);triangle(l,233,120,247,102,266,119,TEAL,255);break;
    case 10:
        triangle(l,192,128,236,68,302,119,CORAL,255);box(l,160,123,156,27,13,0xF9FAFF);
        ellipse(l,301,114,28,28,0xF9FAFF,255);break;
    case 11:box(l,166,140,134,13,6,0xE9EDF7);break;
    default:break;
    }
}
static void draw_effects(lv_event_t *event) {
    lv_layer_t *l=lv_event_get_layer(event);lv_obj_get_coords(scene,&scene_area);
    float t=(draw_clock-clip_started)/1000000.f;
    if(pose.effect==1||pose.effect==2){
        for(unsigned i=0;i<4;i++){
            float u=fmodf(t*.42f+i*.24f,1.f),x=120+i*75+sinf(i*2+t)*8,y=215-u*115;
            lv_opa_t a=(lv_opa_t)(sinf(u*PI)*200);
            if(pose.effect==1)heart(l,x,y,13+i%2*5,CORAL,a);else star(l,x,y,8+i%2*3,GOLD,a);
        }
    }else if(pose.effect==3){
        for(unsigned i=0;i<3;i++){
            float u=fmodf(t*.20f+i*.3f,1),x=310+u*22,y=172-u*59,size=8+u*6;
            lv_opa_t a=(lv_opa_t)(sinf(u*PI)*180);
            line(l,x,y,x+size,y,2,0xBED2E6,a);line(l,x+size,y,x,y+size,2,0xBED2E6,a);line(l,x,y+size,x+size,y+size,2,0xBED2E6,a);
        }
    }else if(pose.effect==4){
        for(unsigned i=0;i<3;i++)ellipse(l,218+i*14,189,6,6,TEAL,(lv_opa_t)(110+100*(.5f+.5f*sinf(t*3-i*.9f))));
    }else if(pose.effect==5){
        box(l,300,189,41,32,9,0xE9EDF7);line(l,311,206,317,212,3,0x529D80,255);line(l,317,212,330,198,3,0x529D80,255);
    }else if(pose.effect==6){
        box(l,290,185,38,37,12,TEAL);line(l,309,193,309,207,3,0xFFFFFF,255);ellipse(l,309,214,3,3,0xFFFFFF,255);
    }else if(pose.effect==7){
        box(l,197,318,72,44,8,0xF8F3E7);line(l,201,324,233,345,2,0xD5AE79,255);line(l,233,345,265,324,2,0xD5AE79,255);
    }else if(pose.effect==8){
        for(unsigned i=0;i<3;i++){float h=10+8*(.5f+.5f*sinf(t*2+i*.9f));box(l,320+i*8,235-h*.5f,4,h,2,TEAL);}
    }
}

static void apply_appearance(void) {
    mochi_appearance_get(&appearance);appearance_seen=mochi_appearance_revision();
    const original_asset_t *next=&original_assets[appearance.color<6?appearance.color:0];
    if(body_asset!=next){body_asset=next;lv_image_set_src(body,&next->image);applied_x=INT32_MIN;}
    show(back,outfit()==11);show(front,outfit()!=0);
    lv_obj_invalidate(front);lv_obj_invalidate(back);face_signature=0;last_draw=0;
}
static float blink(float seconds) {
    /* A deterministic double-blink, with long readable open-eye holds. */
    float p=fmodf(seconds+1.37f,5.9f);
    if(p<.13f)return 1-sinf(p/.13f*PI);
    if(p>.24f&&p<.34f)return 1-sinf((p-.24f)/.10f*PI);
    return 1;
}
static const char *expression(void) {
    const char *id=active?active->id:"idle";
    if(!strncmp(id,"mini_",5))return id+5;
    if(state==MOCHI_IDLE&&!preview&&appearance.expression){
        static const char *const expressions[]={"idle","happy","love","surprised","proud","wink","yawn","annoyed"};
        return expressions[appearance.expression<8?appearance.expression:0];
    }
    return id;
}
static void resolve_pose(int64_t now) {
    float absolute=now/1000000.f,t=(now-clip_started)/1000000.f;
    float strength=appearance.motion==0?1.f:appearance.motion==1?.35f:0.f;
    const char *id=expression();
    pose=(pose_t){.sx=1,.sy=1,.open_left=1,.open_right=1,.curve=3,.blush=.35f,.eye=EYE_OPEN};
    if(!strncmp(active->id,"mini_",5)){pose.mini=true;pose.sx=.72f;pose.sy=.72f;}
    float base=pose.sx;
    pose.y=sinf(absolute*1.55f)*2.f*strength;
    pose.gaze_x=gaze_x;pose.gaze_y=gaze_y;
    if(!strcmp(id,"happy")||!strcmp(id,"finished")){pose.eye=EYE_SMILE;pose.blush=.9f;pose.curve=7;pose.y-=fabsf(sinf(t*4))*9*strength;pose.effect=!strcmp(id,"finished")?2:0;}
    else if(!strcmp(id,"love")){pose.eye=EYE_HEART;pose.blush=1;pose.curve=7;pose.effect=1;}
    else if(!strcmp(id,"surprised")){pose.open_left=pose.open_right=1.23f;pose.mouth_open=24;pose.y-=5*strength;}
    else if(!strcmp(id,"error")){pose.open_left=pose.open_right=.70f;pose.curve=-6;pose.gaze_y=.5f;}
    else if(!strcmp(id,"sleeping")){pose.eye=EYE_CLOSED;pose.curve=0;pose.sx=base*(1+sinf(t*1.2f)*.012f*strength);pose.sy=base*(1-sinf(t*1.2f)*.014f*strength);pose.effect=3;}
    else if(!strcmp(id,"thinking")){pose.gaze_x=-.7f;pose.gaze_y=-1;pose.curve=0;pose.effect=4;}
    else if(!strcmp(id,"question")||!strcmp(id,"approval")){pose.roll=sinf(t*1.5f)*.045f*strength;pose.open_left=.8f;pose.gaze_x=.4f;pose.effect=4;}
    else if(!strcmp(id,"proud")){pose.eye=EYE_SMILE;pose.curve=8;pose.y-=4*strength;pose.effect=2;}
    else if(!strcmp(id,"wink")){pose.open_left=0;pose.curve=6;pose.roll=-.04f*strength;}
    else if(!strcmp(id,"dizzy")){pose.eye=EYE_SPIRAL;pose.roll=sinf(t*5)*.06f*strength;pose.curve=-3;}
    else if(!strcmp(id,"working")){pose.gaze_y=.5f;pose.open_left=pose.open_right=.88f;pose.effect=4;}
    else if(!strcmp(id,"searching")){pose.gaze_x=sinf(t*1.6f);pose.roll=sinf(t*1.6f)*.025f*strength;pose.effect=4;}
    else if(!strcmp(id,"ratelimit")){pose.open_left=pose.open_right=.5f;pose.curve=0;pose.effect=6;}
    else if(!strcmp(id,"yawn")){pose.eye=EYE_CLOSED;pose.mouth_open=10+17*sinf(CLAMP(t/.9f,0,1)*PI*.5f);}
    else if(!strcmp(id,"annoyed")||!strcmp(id,"slap")){pose.brow=true;pose.open_left=pose.open_right=.65f;pose.curve=-4;pose.x=sinf(t*9)*expf(-t*2)*8*strength;}
    else if(!strcmp(id,"dance")){float beat=t*2*PI*112/60;pose.x=sinf(beat*.5f)*12*strength;pose.y=-fabsf(sinf(beat))*9*strength;pose.roll=sinf(beat*.5f)*.07f*strength;pose.eye=EYE_SMILE;pose.curve=7;}
    else if(!strcmp(id,"greet")){pose.roll=sinf(t*6)*expf(-t*.8f)*.075f*strength;pose.curve=6;pose.effect=2;}
    else if(!strcmp(id,"blink")){float b=fmodf(t,1);pose.open_left=pose.open_right=b<.4f?fabsf(cosf(b/.4f*PI)):1;}
    else if(!strcmp(id,"look")){pose.gaze_x=sinf(t*1.5f);pose.gaze_y=cosf(t*1.5f)*.5f;}
    else if(!strcmp(id,"squash")){float k=sinf(t*9)*expf(-t*2)*.12f*strength;pose.sx=base*(1+k);pose.sy=base*(1-k);}
    else if(!strcmp(id,"roll")){pose.roll=2*PI*CLAMP(t/1.7f,0,1)*strength;pose.open_left=pose.open_right=.8f;}
    else if(!strcmp(id,"mailbox")){pose.effect=7;pose.gaze_y=.7f;pose.curve=6;}
    else if(!strcmp(id,"gulp")){pose.mouth_open=8+fabsf(sinf(t*6))*16;pose.sy=base*(1+sinf(t*6)*.025f*strength);}
    else if(!strcmp(id,"update_hint")){pose.effect=5;pose.gaze_x=.7f;pose.gaze_y=-.7f;}
    if(!preview&&state==MOCHI_LISTENING){pose.open_left=pose.open_right=1.08f;pose.effect=8;pose.roll=.025f*strength;}
    if(!preview&&state==MOCHI_OFFLINE){pose.effect=6;pose.curve=-3;}
    if(state==MOCHI_SPEAKING){
        /* The whole body and costume hold still during actual audio output;
         * only the small face region follows DMA and natural blinking. */
        pose.x=0;pose.y=0;pose.sx=base;pose.sy=base;pose.roll=0;pose.effect=0;pose.eye=EYE_OPEN;
        pose.gaze_x=0;pose.gaze_y=0;pose.curve=3;
        static const float mouth_heights[]={0,8,17,26};pose.mouth_open=mouth_heights[mouth_pose];
    }
    if(pose.eye==EYE_OPEN){float b=blink(absolute);pose.open_left*=b;pose.open_right*=b;}
}
static uint32_t signature(void) {
    /* Quantize subpixel changes before invalidating the small face surface. */
    uint32_t h=2166136261u;
    int values[]={(int)(pose.gaze_x*10),(int)(pose.gaze_y*10),(int)(pose.open_left*30),(int)(pose.open_right*30),
        (int)(pose.mouth_open*2),(int)(pose.curve*2),(int)(pose.blush*20),pose.eye,pose.brow,
        (int)(pose.x*2),(int)(pose.y*2),(int)(pose.sx*1000),(int)(pose.sy*1000),(int)(pose.roll*1000),wardrobe_view};
    for(unsigned i=0;i<sizeof(values)/sizeof(values[0]);i++)h=(h^(uint32_t)values[i])*16777619u;
    return h;
}
static void update_geometry(void) {
    float scale=view_scale();
    int px=233-body_asset->x,py=250-body_asset->y;
    int x=lroundf(view_x(233+pose.x))-px,y=lroundf(view_y(250+pose.y))-py;
    int sx=lroundf(256*pose.sx*scale),sy=lroundf(256*pose.sy*scale),roll=lroundf(pose.roll*1800/PI);
    bool changed=x!=applied_x||y!=applied_y||sx!=applied_sx||sy!=applied_sy||roll!=applied_roll;
    if(changed){
        lv_image_set_pivot(body,px,py);lv_obj_set_pos(body,x,y);lv_image_set_scale_x(body,sx);lv_image_set_scale_y(body,sy);lv_image_set_rotation(body,roll);
        applied_x=x;applied_y=y;applied_sx=sx;applied_sy=sy;applied_roll=roll;body_frames++;
        if(outfit()){lv_obj_invalidate(front);if(outfit()==11)lv_obj_invalidate(back);}
    }
    uint32_t next=signature();if(next!=face_signature){face_signature=next;lv_obj_invalidate(face);}
    bool has_effect=pose.effect!=0;
    if(lv_obj_has_flag(effects,LV_OBJ_FLAG_HIDDEN)==has_effect)show(effects,has_effect);
    if(has_effect)lv_obj_invalidate(effects);
}

bool mochi_animation_create(lv_obj_t *parent) {
    if(created)return true;
    scene_home=parent;scene=lv_obj_create(parent);lv_obj_remove_style_all(scene);
    lv_obj_set_size(scene,466,466);lv_obj_remove_flag(scene,LV_OBJ_FLAG_CLICKABLE|LV_OBJ_FLAG_SCROLLABLE);
    back=lv_obj_create(scene);lv_obj_remove_style_all(back);lv_obj_set_size(back,466,466);
    lv_obj_remove_flag(back,LV_OBJ_FLAG_CLICKABLE|LV_OBJ_FLAG_SCROLLABLE);lv_obj_add_event_cb(back,draw_back,LV_EVENT_DRAW_MAIN,NULL);
    body=lv_image_create(scene);lv_obj_remove_flag(body,LV_OBJ_FLAG_CLICKABLE);lv_image_set_antialias(body,true);
    face=lv_obj_create(scene);lv_obj_remove_style_all(face);
    /* Includes both eyes, cheeks, mouth and small gaze changes; a speaking
     * phoneme does not invalidate the whole 466px display or costume. */
    lv_obj_set_pos(face,140,211);lv_obj_set_size(face,190,120);
    lv_obj_remove_flag(face,LV_OBJ_FLAG_CLICKABLE|LV_OBJ_FLAG_SCROLLABLE);lv_obj_add_event_cb(face,draw_face,LV_EVENT_DRAW_MAIN,NULL);
    front=lv_obj_create(scene);lv_obj_remove_style_all(front);lv_obj_set_size(front,466,466);
    lv_obj_remove_flag(front,LV_OBJ_FLAG_CLICKABLE|LV_OBJ_FLAG_SCROLLABLE);lv_obj_add_event_cb(front,draw_front,LV_EVENT_DRAW_MAIN,NULL);
    effects=lv_obj_create(scene);lv_obj_remove_style_all(effects);lv_obj_set_size(effects,466,466);
    lv_obj_remove_flag(effects,LV_OBJ_FLAG_CLICKABLE|LV_OBJ_FLAG_SCROLLABLE);lv_obj_add_event_cb(effects,draw_effects,LV_EVENT_DRAW_MAIN,NULL);show(effects,false);
    active=find_clip("idle");clip_started=esp_timer_get_time();created=true;apply_appearance();
    resolve_pose(clip_started);update_geometry();return true;
}
void mochi_animation_personalize(lv_obj_t *parent) {
    if(!created||wardrobe_view==(parent!=NULL))return;
    wardrobe_view=parent!=NULL;lv_obj_set_parent(scene,parent?parent:scene_home);
    lv_obj_set_pos(scene,wardrobe_view?65:0,wardrobe_view?94:0);lv_obj_set_size(scene,wardrobe_view?336:466,wardrobe_view?176:466);
    lv_obj_set_size(front,wardrobe_view?336:466,wardrobe_view?176:466);lv_obj_set_size(back,wardrobe_view?336:466,wardrobe_view?176:466);
    lv_obj_set_size(effects,wardrobe_view?336:466,wardrobe_view?176:466);
    lv_obj_set_pos(face,wardrobe_view?115:140,wardrobe_view?89:211);lv_obj_set_size(face,wardrobe_view?108:190,wardrobe_view?70:120);
    applied_x=INT32_MIN;face_signature=0;last_draw=0;lv_obj_move_background(scene);
    if(wardrobe_view)mochi_animation_state(MOCHI_IDLE);
    if(animation_timer)lv_timer_ready(animation_timer);
}
void mochi_animation_state(mochi_state_t next) {
    if(!created)return;
    state=(unsigned)next<MOCHI_STATE_COUNT?next:MOCHI_IDLE;preview=false;preview_outfit=-1;
    active=find_clip(state_id(state));clip_started=esp_timer_get_time();
    preview_until=active&&!active->loop?clip_started+(int64_t)active->duration_ms*1000:0;
    mouth_pose=0;apply_appearance();
}
int mochi_animation_duration(mochi_state_t next) {
    const clip_t *clip=find_clip(state_id(next));return clip&&!clip->loop?(int)clip->duration_ms:0;
}
void mochi_animation_look(float x,float y) {
    target_x=CLAMP(x,-1,1);target_y=CLAMP(y,-1,1);last_interaction=esp_timer_get_time();
}
bool mochi_animation_play(const char *id) {
    const clip_t *clip=find_clip(id);if(!clip||!created)return false;
    state=MOCHI_IDLE;active=clip;preview=true;preview_outfit=-1;
    clip_started=esp_timer_get_time();preview_until=clip_started+(int64_t)(clip->duration_ms+200)*1000;
    if(!strcmp(clip->group,"outfit"))for(unsigned i=1;i<12;i++)if(!strcmp(id+7,mochi_appearance_outfit_id(i)))preview_outfit=(int)i;
    frame_dt_index=frame_dt_count=0;apply_appearance();return true;
}
const char *mochi_animation_next(int direction) {
    gallery_index=(gallery_index+CLIP_COUNT+(direction<0?-1:1))%CLIP_COUNT;
    return mochi_animation_play(clips[gallery_index].id)?clips[gallery_index].label:NULL;
}
unsigned mochi_animation_count(void){return CLIP_COUNT;}
const char *mochi_animation_motion_mode(void) {
    mochi_appearance_t p;mochi_appearance_get(&p);return p.motion==0?"normal":p.motion==1?"calm":"still";
}
bool mochi_animation_motion_set(const char *name) {
    if(!name)return false;
    return !strcmp(name,"normal")?mochi_appearance_set(3,0):!strcmp(name,"calm")?mochi_appearance_set(3,1):!strcmp(name,"still")?mochi_appearance_set(3,2):false;
}
bool mochi_animation_uploading(void){return false;}
void mochi_animation_upload_poll(void){}
void mochi_animation_bind_timer(lv_timer_t *timer){animation_timer=timer;}
void mochi_animation_tick(bool visible) {
    if(!created)return;
    int64_t now=esp_timer_get_time();
    mochi_output_status_t output;mochi_audio_output_status(&output);
    mouth_pose=visible&&state==MOCHI_SPEAKING?(output.level_q10<30?0:output.level_q10<110?1:output.level_q10<260?2:3):0;
    mouth_level=output.level_q10;mouth_sequence=output.sequence;mouth_sample_age=output.age_ms;mouth_tick=(unsigned)xTaskGetTickCount();
    if(!visible){last_draw=0;visible_last=false;return;}
    if(preview_until&&now>=preview_until){mochi_set_state(MOCHI_IDLE,0);return;}
    if(appearance_seen!=mochi_appearance_revision())apply_appearance();
    if(now-last_draw<15000)return;
    if(last_draw){frame_dt[frame_dt_index++%64]=(unsigned)(now-last_draw);if(frame_dt_count<64)frame_dt_count++;}
    float dt=last_draw?CLAMP((now-last_draw)/1000000.f,.001f,.1f):.02f;last_draw=now;
    if(now-last_interaction>2200000){target_x=0;target_y=0;}
    float ease=1-expf(-dt*8);gaze_x+=(target_x-gaze_x)*ease;gaze_y+=(target_y-gaze_y)*ease;
    draw_clock=now;resolve_pose(now);update_geometry();
    if(!visible_last){lv_obj_invalidate(scene);visible_last=true;}
    render_us=(unsigned)(esp_timer_get_time()-now);frames++;
}
unsigned mochi_animation_cleanup_storage(void) {
    /* Only obsolete, explicitly named clip-cache files; never preferences,
     * network credentials, downloaded lessons or the original export source. */
    DIR *directory=opendir("/mochi");if(!directory)return 0;
    unsigned count=0;struct dirent *entry;
    while((entry=readdir(directory))){
        const char *name=entry->d_name;
        if(strlen(name)!=21||(name[0]!='c'&&name[0]!='t')||strspn(name+1,"0123456789abcdef")!=16||strcmp(name+17,".gif"))continue;
        char path[40];snprintf(path,sizeof(path),"/mochi/%.21s",name);if(!remove(path))count++;
        vTaskDelay(pdMS_TO_TICKS(5));
    }
    closedir(directory);return count;
}
static void describe(char *text,size_t size) {
    unsigned total=0,worst=0;for(unsigned i=0;i<frame_dt_count;i++){total+=frame_dt[i];if(frame_dt[i]>worst)worst=frame_dt[i];}
    snprintf(text,size,"@animation character=Mochi hardware=1.75-G renderer=native loaded=%d animation=%s frame=%u motion=%s uploading=0 count=%u scale=256 mean_us=%u max_us=%u render_us=%u mask_fast=1 body_frames=%u worker=0 identity=oneworks-bun source=rc.9\n",created,active?active->id:"idle",frames,mochi_animation_motion_mode(),(unsigned)CLIP_COUNT,frame_dt_count?total/frame_dt_count:0,worst,render_us,body_frames);
}
bool mochi_animation_console(const char *command) {
    if(!strcmp(command,"@animation")){
        char text[400];if(esp_lv_adapter_lock(1000)==ESP_OK){describe(text,sizeof(text));esp_lv_adapter_unlock();printf("%s",text);}
    }else if(!strncmp(command,"@animation-play ",16)){
        bool ok=false;if(!mochi_voice_busy()&&esp_lv_adapter_lock(1000)==ESP_OK){mochi_set_state(MOCHI_IDLE,0);ok=mochi_animation_play(command+16);esp_lv_adapter_unlock();}
        printf("@animation_play %s\n",ok?"ok":"unavailable");
    }else if(!strncmp(command,"@animation-motion ",18)){
        printf("@animation_motion %s\n",mochi_animation_motion_set(command+18)?"ok":"invalid_or_unsaved");
    }else if(!strcmp(command,"@mochi-av")){
        mochi_output_status_t output;
        if(esp_lv_adapter_lock(1000)==ESP_OK){
            mochi_audio_output_status(&output);bool speaking=state==MOCHI_SPEAKING;
            unsigned p=mouth_pose,age=mouth_sample_age,level=mouth_level,sequence=mouth_sequence;
            unsigned ui_age=(unsigned)pdTICKS_TO_MS((TickType_t)((unsigned)xTaskGetTickCount()-mouth_tick));
            esp_lv_adapter_unlock();
            printf("@mochi_av tap=%d active=%d level=%u mean=%u dma_age_ms=%u sequence=%u speaking=%d pose=%u ui_age_ms=%u sample_age_ms=%u mouth_level=%u mouth_sequence=%u\n",output.tap_ready,output.active,output.level_q10,output.mean_abs,output.age_ms,output.sequence,speaking,p,ui_age,age,level,sequence);
        }
    }else if(!strcmp(command,"@native-view")){
        if(esp_lv_adapter_lock(1000)==ESP_OK){
            printf("@mochi_native_view wardrobe=%d visible=%d x=%ld y=%ld w=%ld h=%ld scroll_x=%ld scroll_y=%ld parent_scroll_x=%ld parent_scroll_y=%ld body_x=%ld body_y=%ld body_opa=%u body_visible=%d eyes_x=%ld eyes_y=%ld\n",wardrobe_view,lv_obj_is_visible(scene),(long)lv_obj_get_x(scene),(long)lv_obj_get_y(scene),(long)lv_obj_get_width(scene),(long)lv_obj_get_height(scene),(long)lv_obj_get_scroll_x(scene),(long)lv_obj_get_scroll_y(scene),(long)lv_obj_get_scroll_x(lv_obj_get_parent(scene)),(long)lv_obj_get_scroll_y(lv_obj_get_parent(scene)),(long)lv_obj_get_x(body),(long)lv_obj_get_y(body),lv_obj_get_style_image_opa(body,0),lv_obj_is_visible(body),(long)view_x(194.5f),(long)view_y(250.5f));
            esp_lv_adapter_unlock();
        }
    }else if(!strcmp(command,"@appearance")){
        mochi_appearance_t p;mochi_appearance_get(&p);printf("@appearance outfit=%u color=%u expression=%u motion=%u saved=%d\n",p.outfit,p.color,p.expression,p.motion,mochi_appearance_saved());
    }else if(!strncmp(command,"@appearance-set ",16)){
        unsigned field,value;char tail;bool ok=sscanf(command+16,"%u %u %c",&field,&value,&tail)==2&&mochi_appearance_set(field,value);
        printf("@appearance_set %s\n",ok?"ok":"invalid");
    }else if(!strcmp(command,"@appearance-reload")){
        mochi_appearance_init();printf("@appearance_reload ok\n");
    }else if(!strcmp(command,"@animation-abort")){
        printf("@animation_upload aborted\n");
    }else return false;
    fflush(stdout);return true;
}
