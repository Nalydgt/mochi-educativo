#include "mochi_fonts.h"
/* Native Coucou/Mochi motion at device resolution. Original artwork and
 * motion are attributed in licenses/Coucou-MIT.txt and Coucou-ASSETS.md. */
#include "mochi_animation.h"
#include "coucou_motion.h"
#include "mochi_appearance.h"
#include "mochi_audio.h"
#include "mochi_runtime.h"
#include "mochi_display.h"
#include "src/misc/cache/instance/lv_image_cache.h"
#include "esp_heap_caps.h"
#include "esp_lv_adapter.h"
#include "esp_log.h"
#include "esp_random.h"
#include "esp_spiffs.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include <dirent.h>
#include <math.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define PI 3.14159265358979323846f
#define BODY_W 278
#define BODY_H 216
typedef struct {const char *id;int x,y;lv_image_dsc_t image;} native_asset_t;
#include "mochi_native_index.inc"
typedef struct {const char *id,*label,*group;uint32_t duration_ms;bool loop;} native_clip_t;
static const native_clip_t clips[]={
    {"idle","En calma","state",6000,true},
    {"working","Trabajando","state",4000,true},
    {"thinking","Pensando","state",4000,true},
    {"searching","Buscando","state",4000,true},
    {"approval","Pidiendo permiso","state",4000,true},
    {"question","Curiosidad","state",4000,true},
    {"error","Error","state",4000,false},
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
    {"annoyed","Enfado","emote",2800,false},
    {"greet","Saludo con la mano","gesture",2600,false},
    {"blink","Parpadeo","gesture",1000,false},
    {"look","Mirar alrededor","gesture",4800,false},
    {"squash","Rebote elástico","gesture",1500,false},
    {"slap","Golpecito y protesta","gesture",2200,false},
    {"roll","Vuelta completa","gesture",2200,false},
    {"mailbox","Transformación en buzón","gesture",4600,false},
    {"gulp","Buzón y masticación","gesture",3000,false},
    {"dance","Baile a 112 BPM","gesture",6400,true},
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
    {"mini_annoyed","Mini: enfado","mini",6800,true},
    {"update_hint","Aviso de actualización","gesture",3000,false},
};
#define CLIP_COUNT (sizeof(clips)/sizeof(clips[0]))
static lv_obj_t *body,*hands[2],*eyes[2],*smiles[2],*cheeks[2],*figures[2];
static lv_obj_t *spirals[2],*flying[24],*sleep_z[24],*mouth,*slot,*box,*hat_back,*hat_front;
static lv_obj_t *badge,*badge_text,*badge_dots[3];
static lv_image_dsc_t hand_image,heart_image,star_image,spark_image,sweat_image;
static uint32_t *hand_pixels,*heart_pixels,*star_pixels,*spark_pixels,*sweat_pixels;
static lv_point_precise_t spiral_points[2][72];
static uint32_t previous_tint=UINT32_MAX;
static int previous_tint_opacity=-1;
static coucou_motion_t motion;
static mochi_state_t state=MOCHI_IDLE;
static const native_clip_t *active;
static unsigned gallery_index,frames,appearance_seen,mouth_pose,mouth_tick,mouth_sample_age;
static unsigned mouth_level,mouth_sequence;
static unsigned frame_dt[64],frame_dt_index,frame_dt_count;
static unsigned render_us;
static int64_t preview_until,last_draw,last_interaction;
static float target_x,target_y;
static bool preview,created;
static int preview_outfit=-1,current_outfit=-1;
static const native_asset_t *back_asset,*front_asset,*body_asset;
static mochi_appearance_t appearance;
static lv_image_dsc_t body_paint;
static uint8_t *body_pixels;
static const native_asset_t *painted_asset;
static unsigned painted_colour=UINT32_MAX;
typedef struct {
    lv_image_dsc_t image;
    uint8_t *pixels;
    size_t capacity;
    const lv_image_dsc_t *source;
    int scale_x,scale_y,angle,x,y;
    bool ready;
    unsigned generation;
} native_pose_t;
static native_pose_t body_pose,back_pose,front_pose;
typedef struct {uint16_t left,right,opaque_left,opaque_right,offset;} body_mask_row_t;
typedef struct {body_mask_row_t row[BODY_H];uint8_t edge[4096-BODY_H*sizeof(body_mask_row_t)];} body_mask_t;
static body_mask_t *body_mask;
static const native_asset_t *masked_asset;
static bool body_mask_ready;
typedef struct {int sx,sy,angle,x,y;unsigned generation;} pose_job_t;
static native_pose_t async_pose[2];
static QueueHandle_t pose_jobs;
static SemaphoreHandle_t pose_source_lock;
static TaskHandle_t pose_task;
static atomic_int pose_front=-1,pose_ready=-1;
static atomic_bool pose_calculating;
static atomic_uint pose_generation=1;
static bool body_was_transformed;
static float applied_sx=1,applied_sy=1,applied_tilt;
static unsigned async_presented;
static lv_timer_t *animation_timer;
static lv_obj_t *scene,*scene_home;
static bool wardrobe_view;
#define WARDROBE_SCALE .50f
static float view_x(float x){return wardrobe_view?168+(x-233)*WARDROBE_SCALE:x;}
static float view_y(float y){return wardrobe_view?114+(y-240)*WARDROBE_SCALE:y;}
static float view_scale(void){return wardrobe_view?WARDROBE_SCALE:1;}
static void view_size(lv_obj_t *object,float width,float height)
{
    lv_obj_set_size(object,fmaxf(1,width*view_scale()),fmaxf(1,height*view_scale()));
}
static bool speech_frozen;
static float speech_mouth_x,speech_mouth_y;
typedef struct {bool active;float x,y,width,height,min_height;} speech_eye_t;
static speech_eye_t speech_eyes[2];

static const char *const expression_ids[]={"","happy","love","surprised","proud","wink","yawn","annoyed"};
static const uint32_t custom_colours[]={0,0x60ACF0,0xB099F2,0xEDA1C2,0x87CEB0,0xEDC37D};

static const native_asset_t *find_art(const char *id)
{
    for(unsigned i=0;i<sizeof(native_assets)/sizeof(native_assets[0]);i++)if(!strcmp(id,native_assets[i].id))return &native_assets[i];
    return NULL;
}
static const native_clip_t *find_clip(const char *id)
{
    for(unsigned i=0;i<CLIP_COUNT;i++)if(id&&!strcmp(id,clips[i].id))return &clips[i];
    return NULL;
}
static const char *state_id(mochi_state_t value)
{
    static const char *const ids[MOCHI_STATE_COUNT]={"idle","happy","love","surprised","error","sleeping","thinking","question","proud","wink","dizzy","working","idle","error","working","searching","approval","finished","ratelimit","yawn","annoyed","dance"};
    return value<MOCHI_STATE_COUNT?ids[value]:"idle";
}
static cq_state_t motion_state(mochi_state_t value)
{
    static const cq_state_t map[MOCHI_STATE_COUNT]={CQ_IDLE,CQ_IDLE,CQ_IDLE,CQ_IDLE,CQ_ERROR,CQ_SLEEPING,CQ_THINKING,CQ_QUESTION,CQ_IDLE,CQ_IDLE,CQ_DIZZY,CQ_WORKING,CQ_IDLE,CQ_ERROR,CQ_WORKING,CQ_SEARCHING,CQ_APPROVAL,CQ_FINISHED,CQ_RATELIMIT,CQ_IDLE,CQ_IDLE,CQ_IDLE};
    return value<MOCHI_STATE_COUNT?map[value]:CQ_IDLE;
}
typedef struct { float x, y; } shape_point_t;

static bool inside_polygon(const shape_point_t *points, int count, float x, float y)
{
    bool inside=false;
    for(int i=0,j=count-1;i<count;j=i++) {
        if ((points[i].y>y)!=(points[j].y>y) &&
            x<(points[j].x-points[i].x)*(y-points[i].y)/(points[j].y-points[i].y)+points[i].x) inside=!inside;
    }
    return inside;
}

static void make_eye_figures(void)
{
    /* Sample Coucou's original Bezier paths and the stars' exact vertices. */
    shape_point_t heart[42], star[10], spark[10], sweat[42];
    const float size=36;
    for(int side=0;side<2;side++) for(int i=0;i<=20;i++) {
        float t=i/20.0f,u=1-t;
        shape_point_t p0={0,side?-.38f:.38f},p1={side?.5f:-1.05f,side?-.95f:-.15f};
        shape_point_t p2={side?1.05f:-.5f,side?-.15f:-.95f},p3={0,side?.38f:-.38f};
        heart[side*21+i]=(shape_point_t){size*(u*u*u*p0.x+3*u*u*t*p1.x+3*u*t*t*p2.x+t*t*t*p3.x),
            size*(u*u*u*p0.y+3*u*u*t*p1.y+3*u*t*t*p2.y+t*t*t*p3.y)};
    }
    for(int i=0;i<10;i++) {
        float radius=i%2?30*.46f:30*1.05f,angle=-PI/2+i*PI/5;
        star[i]=(shape_point_t){cosf(angle)*radius,sinf(angle)*radius};
        radius=i%2?31.5f*.18f:31.5f*.8f;
        spark[i]=(shape_point_t){cosf(angle)*radius,sinf(angle)*radius};
    }
    for(int side=0;side<2;side++) for(int i=0;i<=20;i++) {
        float t=i/20.0f,u=1-t;
        float start=side?.6f:-1, end=side?-1:.6f;
        sweat[side*21+i]=(shape_point_t){30*2*u*t*(side?-.8f:.8f),
            30*(u*u*start+2*u*t*.2f+t*t*end)};
    }
    heart_pixels=heap_caps_calloc(64*64,4,MALLOC_CAP_SPIRAM);
    star_pixels=heap_caps_calloc(64*64,4,MALLOC_CAP_SPIRAM);
    spark_pixels=heap_caps_calloc(64*64,4,MALLOC_CAP_SPIRAM);
    sweat_pixels=heap_caps_calloc(64*64,4,MALLOC_CAP_SPIRAM);
    if(!heart_pixels || !star_pixels || !spark_pixels || !sweat_pixels) abort();
    for(int y=0;y<64;y++) for(int x=0;x<64;x++) {
        int ha=0,sa=0,pa=0,wa=0;
        for(int dy=0;dy<2;dy++) for(int dx=0;dx<2;dx++) {
            float px=x-32+(dx+.5f)/2,py=y-32+(dy+.5f)/2;
            ha+=inside_polygon(heart,42,px,py);
            sa+=inside_polygon(star,10,px,py);
            pa+=inside_polygon(spark,10,px,py);
            wa+=inside_polygon(sweat,42,px,py);
        }
        heart_pixels[y*64+x]=((uint32_t)(ha*255/4)<<24)|0xFF4D6D;
        star_pixels[y*64+x]=((uint32_t)(sa*255/4)<<24)|0xF7B32B;
        spark_pixels[y*64+x]=((uint32_t)(pa*255/4)<<24)|0xFFFFFF;
        sweat_pixels[y*64+x]=((uint32_t)(wa*255/4)<<24)|0x7CC7FF;
    }
    heart_image = (lv_image_dsc_t){.header = {.magic = LV_IMAGE_HEADER_MAGIC,
        .cf = LV_COLOR_FORMAT_ARGB8888, .w = 64, .h = 64, .stride = 256},
        .data_size = 64*64*4, .data = (const uint8_t *)heart_pixels};
    star_image = heart_image;
    star_image.data = (const uint8_t *)star_pixels;
    spark_image = heart_image;
    spark_image.data = (const uint8_t *)spark_pixels;
    sweat_image = heart_image;
    sweat_image.data = (const uint8_t *)sweat_pixels;
}

static float clampf(float v, float lo, float hi)
{
    return fminf(hi, fmaxf(lo, v));
}

static uint32_t shaded_pixel(float alpha, float red, float green, float blue, int x, int y)
{
    /* Ordered dithering before RGB565 conversion avoids contour bands in gray. */
    static const uint8_t bayer[4][4] = {{0,8,2,10},{12,4,14,6},{3,11,1,9},{15,7,13,5}};
    float d = (bayer[y & 3][x & 3] + .5f) / 16 - .5f;
    uint32_t r = clampf(red + d * 8, 0, 255);
    uint32_t g = clampf(green + d * 4, 0, 255);
    uint32_t b = clampf(blue + d * 8, 0, 255);
    return ((uint32_t)(alpha * 255) << 24) | (r << 16) | (g << 8) | b;
}

static void make_hand_texture(void)
{
    hand_pixels = heap_caps_calloc(64 * 56, sizeof(uint32_t), MALLOC_CAP_SPIRAM);
    if (!hand_pixels) abort();
    for (int y = 0; y < 56; y++) for (int x = 0; x < 64; x++) {
        float nx = (x + .5f - 32) / 31.68f, ny = (y + .5f - 28) / 27.456f;
        float alpha = clampf((1 - sqrtf(nx * nx + ny * ny)) * 27.456f + .5f, 0, 1);
        float gradient = clampf(((nx - .7f) * -1.5f + (ny + .85f) * 1.75f) / 5.3125f, 0, 1);
        hand_pixels[y * 64 + x] = shaded_pixel(alpha, 237 - 41 * gradient,
            237 - 40 * gradient, 239 - 37 * gradient, x, y);
    }
    hand_image = (lv_image_dsc_t){.header = {.magic = LV_IMAGE_HEADER_MAGIC,
        .cf = LV_COLOR_FORMAT_ARGB8888, .w = 64, .h = 56, .stride = 256},
        .data_size = 64 * 56 * 4, .data = (const uint8_t *)hand_pixels};
}

static lv_obj_t *oval(lv_obj_t *parent, int width, int height, uint32_t color)
{
    lv_obj_t *obj = lv_obj_create(parent);
    lv_obj_remove_style_all(obj);
    lv_obj_set_size(obj, width, height);
    lv_obj_set_style_radius(obj, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_color(obj, lv_color_hex(color), 0);
    lv_obj_set_style_bg_opa(obj, LV_OPA_COVER, 0);
    lv_obj_remove_flag(obj, LV_OBJ_FLAG_CLICKABLE | LV_OBJ_FLAG_SCROLLABLE);
    return obj;
}

static void center_at(lv_obj_t *obj, float x, float y)
{
    x=view_x(x);y=view_y(y);
    lv_obj_set_pos(obj, (int)lroundf(x - lv_obj_get_width(obj) / 2.0f),
                  (int)lroundf(y - lv_obj_get_height(obj) / 2.0f));
}

static void show(lv_obj_t *object, bool visible)
{
    if (visible) lv_obj_remove_flag(object, LV_OBJ_FLAG_HIDDEN);
    else lv_obj_add_flag(object, LV_OBJ_FLAG_HIDDEN);
}


/* Keep the body's exact alpha edge in internal RAM and reuse unchanged
 * poses. Full-resolution colour is unchanged; each row writes in batches. */
static bool build_pose(native_pose_t *pose,const lv_image_dsc_t *source,
                       int origin_x,int origin_y,int scale_x,int scale_y,int rotation,bool smooth)
{
    if(pose->ready && pose->source==source && pose->scale_x==scale_x && pose->scale_y==scale_y && pose->angle==rotation)return true;
    float sx,sy;
        sx=fmaxf(1,scale_x)/256.0f;sy=fmaxf(1,scale_y)/256.0f;
        float a=rotation*PI/1800,ct=cosf(a),st=sinf(a);
        float lo_x=1e9f,lo_y=1e9f,hi_x=-1e9f,hi_y=-1e9f;
        for(int i=0;i<4;i++){
            float x=(origin_x+(i&1?source->header.w:0))*sx;
            float y=(origin_y+(i&2?source->header.h:0))*sy;
            float tx=ct*x-st*y,ty=st*x+ct*y;
            lo_x=fminf(lo_x,tx);lo_y=fminf(lo_y,ty);hi_x=fmaxf(hi_x,tx);hi_y=fmaxf(hi_y,ty);
        }
        int left=(int)floorf(lo_x)-1,top=(int)floorf(lo_y)-1;
        unsigned w=((unsigned)((int)ceilf(hi_x)-left+2))&~1u;
        unsigned h=(unsigned)((int)ceilf(hi_y)-top+1);
        if(source==&body_paint){
            /* Quantized bounds avoid relayout for tiny changes without
             * sending wide transparent margins through the round display.
             * The smaller 16-pixel blocks also keep clothed dances fluid. */
            w=((unsigned)ceilf(fmaxf(fabsf(lo_x),fabsf(hi_x))*2)+17)&~15u;
            h=((unsigned)ceilf(fmaxf(fabsf(lo_y),fabsf(hi_y))*2)+17)&~15u;
            left=-(int)(w/2);top=-(int)(h/2);
        }
        size_t bytes=(size_t)w*h*3;
        if(w>512 || h>512 || !w || !h)return false;
        if(bytes>pose->capacity){
            size_t capacity=(bytes+16383)&~(size_t)16383;
            uint8_t *pixels=heap_caps_realloc(pose->pixels,capacity,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
            if(!pixels)return false;
            pose->pixels=pixels;pose->capacity=capacity;
        }
        const unsigned source_w=source->header.w,source_h=source->header.h;
        bool fast_body=source==&body_paint && body_mask_ready && !smooth;
        const uint8_t *restrict source_alpha=source->data+source_w*source_h*2;
        uint16_t *restrict result_colour=(uint16_t *)pose->pixels;
        uint8_t *restrict result_alpha=pose->pixels+w*h*2;
        int32_t du=(int32_t)lroundf(ct/sx*65536),dv=(int32_t)lroundf(-st/sy*65536);
        const uint16_t *restrict body_colour=(const uint16_t *)source->data;
        for(unsigned y=0;y<h;y++){
            float px=left+.5f,py=top+(int)y+.5f;
            int32_t u=(int32_t)lroundf(((ct*px+st*py)/sx-origin_x)*65536);
            int32_t v=(int32_t)lroundf(((-st*px+ct*py)/sy-origin_y)*65536);
            for(unsigned bx=0;bx<w;bx+=64){
                unsigned length=w-bx<64?w-bx:64;uint16_t colours[64];uint8_t alphas[64];
                if(fast_body){
                    for(unsigned x=0;x<length;x++,u+=du,v+=dv){
                        unsigned ix=(unsigned)(u>>16),iy=(unsigned)(v>>16);uint8_t alpha=0;uint16_t colour=0;
                        if(iy<source_h){
                            const body_mask_row_t *r=&body_mask->row[iy];
                            if(ix>=r->left && ix<=r->right){
                                colour=body_colour[iy*source_w+ix];
                                alpha=ix<r->opaque_left?body_mask->edge[r->offset+ix-r->left]:
                                      ix>r->opaque_right?body_mask->edge[r->offset+r->opaque_left-r->left+ix-r->opaque_right-1]:255;
                            }
                        }
                        colours[x]=colour;alphas[x]=alpha;
                    }
                }else for(unsigned x=0;x<length;x++,u+=du,v+=dv){
                    unsigned ix=(unsigned)(u>>16),iy=(unsigned)(v>>16);
                    if(ix<source_w && iy<source_h){
                        unsigned n=iy*source_w+ix;colours[x]=body_colour[n];alphas[x]=source_alpha[n];
                        if(smooth){
                            /* Average the source's 2x2 RGB565 dither pattern
                             * when reducing the wardrobe preview. Alpha-weighted
                             * colour keeps transparent edges free of dark halos. */
                            unsigned ar=0,ag=0,ab=0,alpha=0;
                            unsigned px=ix?ix-1:0,py=iy?iy-1:0;
                            for(unsigned dy=0;dy<2;dy++)for(unsigned dx=0;dx<2;dx++){
                                unsigned sx=px+dx,sy=py+dy;
                                if(sx>=source_w || sy>=source_h)continue;
                                unsigned at=sy*source_w+sx,a=source_alpha[at],c=body_colour[at];
                                ar+=(c>>11)*a;ag+=((c>>5)&63)*a;ab+=(c&31)*a;alpha+=a;
                            }
                            alphas[x]=(alpha+2)/4;
                            colours[x]=alpha?((ar+alpha/2)/alpha<<11)|((ag+alpha/2)/alpha<<5)|((ab+alpha/2)/alpha):0;
                        }
                    }
                    else {colours[x]=0;alphas[x]=0;}
                }
                memcpy(result_colour+y*w+bx,colours,length*2);
                memcpy(result_alpha+y*w+bx,alphas,length);
            }
        }
        pose->image=(lv_image_dsc_t){.header={.magic=LV_IMAGE_HEADER_MAGIC,.cf=LV_COLOR_FORMAT_RGB565A8,.w=w,.h=h,.stride=w*2},.data_size=bytes,.data=pose->pixels};
        pose->source=source;pose->scale_x=scale_x;pose->scale_y=scale_y;pose->angle=rotation;
        pose->x=left;pose->y=top;pose->ready=true;

    return true;
}
static void pose_worker(void *argument)
{
    (void)argument;pose_job_t job;
    for(;;){
        if(xQueueReceive(pose_jobs,&job,portMAX_DELAY)!=pdTRUE)continue;
        bool published=false;
        xSemaphoreTake(pose_source_lock,portMAX_DELAY);
        if(job.generation==atomic_load(&pose_generation)){
            int front=atomic_load(&pose_front),back=front==0?1:0;
            native_pose_t *pose=&async_pose[back];
            if(pose->generation!=job.generation)pose->source=NULL;
            if(build_pose(pose,&body_paint,job.x,job.y,job.sx,job.sy,job.angle,false)){
                pose->generation=job.generation;
                if(job.generation==atomic_load(&pose_generation)){atomic_store(&pose_ready,back);published=true;}
            }
        }
        xSemaphoreGive(pose_source_lock);
        if(!published)atomic_store(&pose_calculating,false);
        else if(animation_timer && esp_lv_adapter_lock(1)==ESP_OK){
            /* Present a completed frame without waiting for another UI period.
             * The source mutex is already released before taking the UI lock. */
            lv_timer_ready(animation_timer);
            lv_timer_ready(lv_display_get_refr_timer(lv_obj_get_display(body)));
            esp_lv_adapter_unlock();
        }
    }
}
static void retire_body_pose(lv_obj_t *object)
{
    if(lv_image_get_src(object)!=&body_paint)lv_image_set_src(object,&body_paint);
    int front=atomic_exchange(&pose_front,-1),ready=atomic_exchange(&pose_ready,-1);
    if(front>=0)lv_image_cache_drop(&async_pose[front].image);
    if(ready>=0 && ready!=front)lv_image_cache_drop(&async_pose[ready].image);
    if(ready>=0)atomic_store(&pose_calculating,false);
}
static void paint_body_async(lv_obj_t *object,int origin_x,int origin_y,float cx,float cy,int sx,int sy,int angle)
{
    if(sx==256 && sy==256 && angle%3600==0){
        if(body_was_transformed)atomic_fetch_add(&pose_generation,1);
        body_was_transformed=false;retire_body_pose(object);
        lv_obj_set_pos(object,(int)lroundf(cx+origin_x),(int)lroundf(cy+origin_y));
        applied_sx=applied_sy=1;applied_tilt=0;return;
    }
    body_was_transformed=true;
    unsigned generation=atomic_load(&pose_generation);
    int completed=atomic_exchange(&pose_ready,-1);
    if(completed>=0){
        native_pose_t *next=&async_pose[completed];
        lv_image_cache_drop(&next->image);
        if(next->generation==generation){
            int retired=atomic_exchange(&pose_front,completed);
            lv_image_set_src(object,&next->image);async_presented++;
            if(retired>=0 && retired!=completed)lv_image_cache_drop(&async_pose[retired].image);
        }
        atomic_store(&pose_calculating,false);
    }
    int front=atomic_load(&pose_front);
    if(front>=0 && async_pose[front].generation==generation){
        native_pose_t *pose=&async_pose[front];
        lv_obj_set_pos(object,(int)lroundf(cx+pose->x),(int)lroundf(cy+pose->y));
        applied_sx=pose->scale_x/256.0f;applied_sy=pose->scale_y/256.0f;applied_tilt=pose->angle*PI/1800;
    }else{
        if(lv_image_get_src(object)!=&body_paint)lv_image_set_src(object,&body_paint);
        int retired=atomic_exchange(&pose_front,-1);
        if(retired>=0)lv_image_cache_drop(&async_pose[retired].image);
        lv_obj_set_pos(object,(int)lroundf(cx+origin_x),(int)lroundf(cy+origin_y));
        applied_sx=applied_sy=1;applied_tilt=0;
    }
    if(front>=0 && async_pose[front].generation==generation &&
       async_pose[front].scale_x==sx && async_pose[front].scale_y==sy && async_pose[front].angle==angle)return;
    bool expected=false;
    if(atomic_compare_exchange_strong(&pose_calculating,&expected,true)){
        pose_job_t job={.sx=sx,.sy=sy,.angle=angle,.x=origin_x,.y=origin_y,.generation=generation};
        if(xQueueOverwrite(pose_jobs,&job)!=pdPASS)atomic_store(&pose_calculating,false);
    }
}
static void paint_layer(lv_obj_t *object,native_pose_t *pose,const lv_image_dsc_t *source,
                        int origin_x,int origin_y,float cx,float cy,float sx,float sy,float angle)
{
    cx=view_x(cx);cy=view_y(cy);
    if(wardrobe_view){sx*=WARDROBE_SCALE;sy*=WARDROBE_SCALE;}
    int scale_x=(int)lroundf(sx*256),scale_y=(int)lroundf(sy*256),rotation=(int)lroundf(angle*1800/PI);
    lv_image_set_scale(object,256);lv_image_set_rotation(object,0);
    if(source==&body_paint && pose_task && !wardrobe_view){paint_body_async(object,origin_x,origin_y,cx,cy,scale_x,scale_y,rotation);return;}
    if(scale_x==256 && scale_y==256 && rotation%3600==0){
        if(lv_image_get_src(object)!=source)lv_image_set_src(object,source);
        lv_obj_set_pos(object,(int)lroundf(cx+origin_x),(int)lroundf(cy+origin_y));return;
    }
    bool changed=!pose->ready || pose->source!=source || pose->scale_x!=scale_x || pose->scale_y!=scale_y || pose->angle!=rotation;
    if(changed){
        lv_image_cache_drop(&pose->image);
        if(!build_pose(pose,source,origin_x,origin_y,scale_x,scale_y,rotation,wardrobe_view))return;
    }
    if(changed || lv_image_get_src(object)!=&pose->image)lv_image_set_src(object,&pose->image);
    lv_obj_set_pos(object,(int)lroundf(cx+pose->x),(int)lroundf(cy+pose->y));
}
static void refresh_body_art(void)
{
    if(!body_asset || !body_pixels || (painted_asset==body_asset && painted_colour==appearance.color))return;
    if(pose_source_lock)xSemaphoreTake(pose_source_lock,portMAX_DELAY);
    body_paint=body_asset->image;
    memcpy(body_pixels,body_paint.data,body_paint.data_size);
    if(appearance.color){
        uint32_t tint=custom_colours[appearance.color];
        unsigned tr=(tint>>16)&255,tg=(tint>>8)&255,tb=tint&255;
        uint16_t *pixels=(uint16_t *)body_pixels;
        for(unsigned i=0;i<BODY_W*BODY_H;i++){
            unsigned c=pixels[i],r=(c>>11)*255/31,g=((c>>5)&63)*255/63,b=(c&31)*255/31;
            r=(r*155+tr*100+127)/255;g=(g*155+tg*100+127)/255;b=(b*155+tb*100+127)/255;
            pixels[i]=(uint16_t)(((r*31+127)/255<<11)|((g*63+127)/255<<5)|((b*31+127)/255));
        }
    }
    body_paint.data=body_pixels;painted_asset=body_asset;painted_colour=appearance.color;body_pose.ready=false;body_pose.source=NULL;
    if(body_mask && masked_asset!=body_asset){
        const uint8_t *alpha=body_pixels+BODY_W*BODY_H*2;unsigned used=0;body_mask_ready=true;
        for(unsigned y=0;y<BODY_H;y++){
            const uint8_t *row=alpha+y*BODY_W;unsigned left=0,right=BODY_W;
            while(left<BODY_W && !row[left])left++;
            while(right>left && !row[right-1])right--;
            unsigned first=left,last=right;
            while(first<right && row[first]!=255)first++;
            while(last>first && row[last-1]!=255)last--;
            unsigned count=first-left+right-last;
            if(used+count>sizeof(body_mask->edge)){body_mask_ready=false;break;}
            body_mask->row[y]=(body_mask_row_t){.left=left,.right=right?right-1:0,.opaque_left=first,.opaque_right=last?last-1:0,.offset=used};
            memcpy(body_mask->edge+used,row+left,first-left);used+=first-left;
            memcpy(body_mask->edge+used,row+last,right-last);used+=right-last;
            for(unsigned x=first;x<last;x++)if(row[x]!=255)body_mask_ready=false;
        }
        masked_asset=body_asset;
    }
    atomic_fetch_add(&pose_generation,1);body_was_transformed=false;
    lv_image_cache_drop(&body_paint);retire_body_pose(body);
    if(pose_source_lock)xSemaphoreGive(pose_source_lock);
}
static void select_outfit(unsigned index,bool transition)
{
    if((int)index==current_outfit)return;
    current_outfit=index;
    char id[64];
    snprintf(id,sizeof(id),"%s_back",mochi_appearance_outfit_id(index));back_asset=find_art(id);
    snprintf(id,sizeof(id),"%s_front",mochi_appearance_outfit_id(index));front_asset=find_art(id);
    if(back_asset){lv_image_set_src(hat_back,&back_asset->image);lv_image_set_pivot(hat_back,-back_asset->x,-back_asset->y);}
    if(front_asset){lv_image_set_src(hat_front,&front_asset->image);lv_image_set_pivot(hat_front,-front_asset->x,-front_asset->y);}
    body_asset=find_art(index==9?"pumpkin_body":"body");refresh_body_art();
    if(transition)coucou_motion_outfit(&motion,index>0);
    else motion.value[CQ_OUTFIT]=1;
}
static void paint_outfits(float cx,float cy,float sx,float sy,float tilt,float morph)
{
    float presence=motion.value[CQ_OUTFIT];
    float p=fminf(1,fmaxf(0,presence));
    float alpha=fminf(1,p*2.5f)*(1-fminf(1,fmaxf(0,(morph-.3f)/.2f)));
    bool visible=current_outfit>0&&!motion.mini&&alpha>.005f;
    const native_asset_t *a[]={back_asset,front_asset};lv_obj_t *objects[]={hat_back,hat_front};
    for(int i=0;i<2;i++){
        show(objects[i],visible&&a[i]);
        if(!visible||!a[i])continue;
        float s=current_outfit==4||current_outfit==5||current_outfit==6||current_outfit==7||current_outfit==9?1:.85f+.15f*p;
        float dy=(1-p)*-105.6f;
        if(current_outfit==4||current_outfit==5||current_outfit==7)dy=(1-p)*26;
        if(current_outfit==6)s=p;
        paint_layer(objects[i],i?&front_pose:&back_pose,&a[i]->image,a[i]->x,a[i]->y,
                    cx+motion.value[CQ_YAW]*12,cy+dy,sx*s,sy*s,tilt);
        lv_obj_set_style_image_opa(objects[i],(int)(alpha*255),0);
    }
}
static void paint_badge(float cx,float cy,float radius,float seconds)
{
    bool update=active&&!strcmp(active->id,"update_hint");
    bool dots=motion.state==CQ_WORKING||motion.state==CQ_THINKING||motion.state==CQ_SEARCHING;
    bool visible=update || (motion.state!=CQ_IDLE&&motion.state!=CQ_SLEEPING&&motion.state!=CQ_DIZZY);
    float scale=motion.value[CQ_BADGE];
    visible=visible&&scale>.02f&&motion.value[CQ_MORPH]<.25f;
    show(badge,visible);
    if(!visible)return;
    uint32_t colour=((uint32_t)(motion.color[0]*255)<<16)|((uint32_t)(motion.color[1]*255)<<8)|(uint32_t)(motion.color[2]*255);
    lv_obj_set_style_bg_color(badge,lv_color_hex(update?0x3B9DF5:colour),0);
    lv_obj_set_style_transform_scale(badge,(int)(256*scale),0);
    center_at(badge,cx+radius*.91f,cy-radius*.76f);
    const char *text=dots?"":motion.state==CQ_QUESTION?"?":motion.state==CQ_APPROVAL?"!":update?LV_SYMBOL_UP:LV_SYMBOL_OK;
    if(strcmp(lv_label_get_text(badge_text),text))lv_label_set_text(badge_text,text);
    lv_obj_center(badge_text);
    for(int i=0;i<3;i++){
        show(badge_dots[i],dots);
        lv_obj_set_pos(badge_dots[i],7+i*8,15+(int)(sinf(seconds*5-i)*2));
    }
}
static void apply_appearance(void)
{
    speech_frozen=false;
    mochi_appearance_get(&appearance);appearance_seen=mochi_appearance_revision();
    motion.motion_mode=preview?0:appearance.motion;
    coucou_motion_permanent(&motion,expression_ids[appearance.expression]);
    if(preview_outfit<0)select_outfit(appearance.outfit,true);
    refresh_body_art();
    previous_tint=UINT32_MAX;previous_tint_opacity=-1;
}
static void render_native(lv_timer_t *timer)
{
    (void)timer;
    int64_t now=esp_timer_get_time();
    float seconds=now/1000000.0f;
    motion.look_x=now-last_interaction>5000000?0:target_x;
    motion.look_y=now-last_interaction>5000000?0:-target_y;
    coucou_motion_step(&motion, now / 1000000.0);
    const float *v = motion.value;
    const float radius = 120, rx = radius * 1.14f, ry = radius * .88f;
    float cx = 233 + v[CQ_OX] * radius, cy = 233 + v[CQ_OY] * radius + radius * .06f;
    float scene_scale=current_outfit==8?.9f:1;
    float sx = v[CQ_SX]*scene_scale, sy = v[CQ_SY]*scene_scale, tilt = v[CQ_TILT];
    float morph=v[CQ_MORPH];
    bool rigid=current_outfit>0 && !motion.mini;
    if(rigid)tilt+=v[CQ_ROLL];
    /* Keep the large body still during the peek wave. Only the small hand
     * regions need new pixels while they move, so QSPI can clear the scan. */
    if (motion.greeting) tilt = 0;
    if (motion.dance_level > .001f) {
        float beat = seconds * 112 / 60, hop = fabsf(sinf(PI * beat)), land = powf(1-hop, 6);
        cx += .08f * radius * sinf(PI * beat) * motion.dance_level;
        cy -= .2f * radius * hop * motion.dance_level;
        tilt += .1f * sinf(PI * beat) * motion.dance_level;
        sx *= 1 + .045f * land * motion.dance_level;
        sy *= 1 - .06f * land * motion.dance_level;
    }
    paint_layer(body,&body_pose,&body_paint,-BODY_W/2,-BODY_H/2,cx,cy,sx,sy,tilt);
    if(pose_task && !wardrobe_view){sx=applied_sx;sy=applied_sy;tilt=applied_tilt;}
    float ct=cosf(tilt),st=sinf(tilt);
    uint32_t tint = ((uint32_t)(motion.color[0]*255) << 16) | ((uint32_t)(motion.color[1]*255) << 8) | (uint32_t)(motion.color[2]*255);
    int tint_opacity = (int)(v[CQ_TINT] * 110);
    if(appearance.color){tint=custom_colours[appearance.color];tint_opacity=100;}
    if (tint_opacity && tint != previous_tint) {
        lv_obj_set_style_image_recolor(body, lv_color_hex(tint), 0);
        for(int hand=0;hand<2;hand++)lv_obj_set_style_image_recolor(hands[hand],lv_color_hex(tint),0);
        previous_tint = tint;
    }
    if (tint_opacity != previous_tint_opacity) {
        lv_obj_set_style_image_recolor_opa(body, appearance.color?0:tint_opacity, 0);
        for(int hand=0;hand<2;hand++)lv_obj_set_style_image_recolor_opa(hands[hand],tint_opacity,0);
        previous_tint_opacity = tint_opacity;
    }

    lv_obj_set_style_image_opa(body,(int)((1-morph)*255),0);
    show(box,morph>.005f);
    if(morph>.005f){
        view_size(box,240*sx,225.6f*sy);
        lv_obj_set_style_radius(box,(int)(17*view_scale()),0);lv_obj_set_style_bg_opa(box,(int)(morph*255),0);
        lv_obj_set_style_transform_rotation(box,(int)(tilt*1800/PI),0);
        center_at(box,cx,cy);
    }
    show(slot,morph>.05f && motion.slot>.006f);
    if(morph>.05f && motion.slot>.006f){
        int sw=(int)(216*morph*sx),sh=(int)(motion.slot*radius*morph*sy);
        view_size(slot,sw,sh>1?sh:1);
        center_at(slot,cx,cy-radius*(.88f+.06f*morph)+radius*.08f*morph+sh/2);
    }
    /* Large rotating costume rasters can dominate the ESP32's frame budget.
     * During dancing keep their fitted shape and follow the body's bounce;
     * the body, eyes and hands retain the original dance motion. */
    if(motion.dance_level>.15f && current_outfit>0)
        paint_outfits(cx,cy,scene_scale,scene_scale,0,morph);
    else paint_outfits(cx,cy,sx,sy,tilt,morph);
    paint_badge(cx,cy,radius,seconds);
    bool waving = motion.now >= motion.wave_start && motion.wave_start > 0 && motion.now < motion.wave_until;
    for (int i=0;i<2;i++) {
        float side = i ? 1 : -1;
        float hx = side * rx * sx * 1.08f, hy = ry * sy * .7f;
        float hand_rotation = 0;
        if (waving) {
            float wt = motion.now-motion.wave_start;
            if (i) {
                float rise=1-powf(1-fminf(1,wt/.18f),3);
                hx += (rx*sx*1.1f+cosf(13*wt)*.06f*2*ry-hx)*rise;
                hy += (-ry*sy*.15f-sinf(13*wt)*.14f*2*ry-hy)*rise;
                hand_rotation = (-.5f+sinf(13*wt)*.35f)*rise;
                /* The round-panel adaptation keeps the waving ellipse clear
                 * of the foreground body instead of cutting it in half. */
                float clear_x = fmaxf(hx + 20, rx*sx + .3f*ry*v[CQ_HANDS] + 3);
                hx += (clear_x - hx) * rise;
            } else hy += sinf(6*wt)*.04f*2*ry;
        }
        lv_image_set_scale(hands[i], fmaxf(1, 256*v[CQ_HANDS]*view_scale()));
        lv_image_set_rotation(hands[i], (int)(hand_rotation*1800/PI));
        center_at(hands[i], cx+ct*hx-st*hy, cy+st*hx+ct*hy);
        show(hands[i], v[CQ_HANDS] > .01f);

        float eye_yaw=side*.37f+v[CQ_YAW], eye_pitch=-.12f+v[CQ_PITCH]+(rigid?0:v[CQ_ROLL]);
        float cp=cosf(eye_pitch), fx=fmaxf(.18f,cosf(eye_yaw)), fy=fmaxf(.18f,cp);
        bool visible=cosf(eye_yaw)*cp>.04f;
        float local_x=sinf(eye_yaw)*cp*rx*sx, local_y=-sinf(eye_pitch)*ry*sy;
        float ex=cx+ct*local_x-st*local_y, ey=cy+st*local_x+ct*local_y+ry*.14f*morph;
        float w=radius*.25f*v[CQ_ES]*(motion.mini?1.9f:1), h=radius*.27f*v[CQ_ES]*(motion.mini?1.9f:1);
        cq_eye_t shape=motion.eye;
        if(motion.dance_level>.15f && (motion.state==CQ_IDLE || motion.state==CQ_FINISHED)) shape=CQ_HAPPY;
        bool arc=shape==CQ_HAPPY || shape==CQ_CLOSED || shape==CQ_CUP || (shape==CQ_WINK && i==1);
        bool figure=shape==CQ_HEART || shape==CQ_STAR;
        bool spiral=shape==CQ_SPIRAL;
        float ew=w, eh=fmaxf(h*v[CQ_OPEN],w*.3f);
        if(shape==CQ_WIDE) {ew*=1.16f; eh*=1.12f;}
        if(shape==CQ_DOT) ew=eh=w*.9f;
        if(shape==CQ_LINE) {ew=w*1.56f;eh=w*.42f;}
        if(shape==CQ_FLAT) {ew=w*1.44f;eh=w*.4f;}
        if(shape==CQ_TIRED) eh=h*.38f;
        speech_eyes[i]=(speech_eye_t){
            .active=visible && (shape==CQ_PILL || shape==CQ_WIDE || (shape==CQ_WINK && i==0)),
            .x=ex,.y=ey,.width=ew*fx*sx,
            .height=h*fy*sy*(shape==CQ_WIDE?1.12f:1),
            .min_height=w*.3f*fy*sy*(shape==CQ_WIDE?1.12f:1)};
        show(eyes[i],visible && !arc && !figure && !spiral);
        show(smiles[i],visible && arc);
        show(figures[i],visible && figure);
        show(spirals[i],visible && spiral);
        if(visible && !arc && !figure && !spiral){
            view_size(eyes[i],ew*fx*sx,eh*fy*sy);
            lv_obj_set_style_transform_rotation(eyes[i],(int)((tilt+(shape==CQ_LINE?-side*.2f:0))*1800/PI),0);
            center_at(eyes[i],ex,ey);
        }else if(visible && arc){
            int arc_size=(int)(w*2.14f),degrees=(int)lroundf(tilt*180/PI);
            view_size(smiles[i],arc_size,arc_size);
            lv_obj_set_style_arc_width(smiles[i],fmaxf(1,w*(shape==CQ_CLOSED?.36f:.5f)*view_scale()),LV_PART_INDICATOR);
            /* A circular arc rotates by changing its angles. This avoids a
             * temporary bitmap and a second transform for every smiling eye. */
            int first=(shape==CQ_CLOSED||shape==CQ_CUP?27:202)+degrees;
            int last=(shape==CQ_CLOSED||shape==CQ_CUP?153:338)+degrees;
            lv_arc_set_angles(smiles[i],(first%360+360)%360,(last%360+360)%360);
            center_at(smiles[i],ex,ey+h*(shape==CQ_CLOSED?-.08f:.18f));
        }else if(visible && figure){
            const lv_image_dsc_t *eye_art=shape==CQ_STAR?&star_image:&heart_image;
            if(lv_image_get_src(figures[i])!=eye_art)lv_image_set_src(figures[i],eye_art);
            lv_image_set_scale_x(figures[i],(int)(256*fx*sx*v[CQ_ES]*view_scale()));
            lv_image_set_scale_y(figures[i],(int)(256*fy*sy*v[CQ_ES]*view_scale()));
            lv_image_set_rotation(figures[i],(int)((tilt+(shape==CQ_STAR?seconds*1.5f*side:0))*1800/PI));
            center_at(figures[i],ex,ey);
        }else if(visible && spiral){
            for(int n=0;n<70;n++){
                float a=n*.2f,r=w*.06f+a*w*.058f,aa=a+seconds*9*side;
                spiral_points[i][n]=(lv_point_precise_t){32+cosf(aa)*r*view_scale(),32+sinf(aa)*r*view_scale()};
            }
            lv_line_set_points(spirals[i],spiral_points[i],70);
            lv_obj_set_style_line_width(spirals[i],fmaxf(1,w*.22f*view_scale()),0);center_at(spirals[i],ex,ey);
        }
        view_size(cheeks[i],38,18);center_at(cheeks[i],cx+side*rx*.55f+sinf(v[CQ_YAW])*rx*.8f,cy+ry*.2f);
        lv_obj_set_style_bg_opa(cheeks[i],(int)(fmaxf(v[CQ_BLUSH],v[CQ_TINT]*.5f)*127),0);
    }
    for(int i=0;i<24;i++) {
        cq_particle_t *p=&motion.particles[i];
        bool visible=p->active && p->age>0;
        show(flying[i],visible && p->kind!=4);
        show(sleep_z[i],visible && p->kind==4);
        if(!visible) continue;
        float k=p->age/p->life, alpha=k<.2f?k/.2f:1-(k-.2f)/.8f;
        float px=cx+(p->x+p->vx*p->age)*radius*1.3f;
        float py=cy+(p->y+p->vy*p->age)*radius*1.3f;
        float size=radius*p->size*(1+k*.4f);
        lv_obj_t *object=p->kind==4?sleep_z[i]:flying[i];
        center_at(object,px,py);
        lv_obj_set_style_opa(object,(int)(fminf(1,fmaxf(0,alpha))*255),0);
        if(p->kind!=4) {
            const lv_image_dsc_t *images[]={&heart_image,&star_image,&spark_image,&sweat_image};
            const float sizes[]={36,31.5f,31.5f,30};
            float angle=p->kind==0?sinf(p->age*6)*.3f:
                p->kind==1?p->rotation+p->age*2:p->kind==2?p->rotation:0;
            if(lv_image_get_src(object)!=images[p->kind])lv_image_set_src(object,images[p->kind]);
            lv_image_set_scale(object,(int)(256*size/sizes[p->kind]*view_scale()));
            lv_image_set_rotation(object,(int)(angle*1800/PI));
        }
    }
    speech_mouth_x=233+v[CQ_OX]*120+v[CQ_YAW]*5;
    speech_mouth_y=290+v[CQ_OY]*120;
    frames++;
}


bool mochi_animation_create(lv_obj_t *screen)
{
    scene_home=screen;scene=lv_obj_create(screen);lv_obj_remove_style_all(scene);
    lv_obj_set_size(scene,466,466);lv_obj_set_pos(scene,0,0);
    lv_obj_remove_flag(scene,LV_OBJ_FLAG_CLICKABLE|LV_OBJ_FLAG_SCROLLABLE);
    screen=scene;
    body_mask=heap_caps_malloc(sizeof(body_mask_t),MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
    pose_source_lock=xSemaphoreCreateMutex();pose_jobs=xQueueCreate(1,sizeof(pose_job_t));
    make_hand_texture();make_eye_figures();
    for (int i = 0; i < 2; i++) {
        hands[i] = lv_image_create(screen);
        lv_image_set_src(hands[i], &hand_image);
        lv_image_set_antialias(hands[i], true);
        lv_obj_remove_flag(hands[i], LV_OBJ_FLAG_CLICKABLE);
    }
    hat_back=lv_image_create(screen);lv_obj_remove_flag(hat_back,LV_OBJ_FLAG_CLICKABLE);
    body = lv_image_create(screen);
    body_pixels=heap_caps_malloc(BODY_W*BODY_H*3,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    if(!body_pixels)return false;
    body_asset=find_art("body");refresh_body_art();
    lv_obj_remove_flag(body, LV_OBJ_FLAG_CLICKABLE);
    lv_image_set_antialias(body,false);
    box=oval(screen,240,226,0xD4D5DB);
    lv_obj_set_style_bg_grad_dir(box,LV_GRAD_DIR_VER,0);lv_obj_set_style_bg_grad_color(box,lv_color_hex(0xBFC1CA),0);show(box,false);
    slot=oval(screen,216,2,0x08090C);show(slot,false);

    for (int i = 0; i < 2; i++) {
        cheeks[i] = oval(screen, 38, 18, 0xFF7896);
        eyes[i] = oval(screen, 30, 33, 0x1A1412);
        figures[i] = lv_image_create(screen);
        lv_image_set_src(figures[i], &heart_image);
        lv_obj_remove_flag(figures[i], LV_OBJ_FLAG_CLICKABLE);
        lv_obj_add_flag(figures[i], LV_OBJ_FLAG_HIDDEN);
        spirals[i] = lv_line_create(screen);
        lv_obj_remove_style_all(spirals[i]);
        lv_obj_set_size(spirals[i],64,64);
        lv_obj_set_style_line_color(spirals[i],lv_color_hex(0x1A1412),0);
        lv_obj_set_style_line_rounded(spirals[i],true,0);
        lv_obj_remove_flag(spirals[i],LV_OBJ_FLAG_CLICKABLE);
        lv_obj_add_flag(spirals[i],LV_OBJ_FLAG_HIDDEN);
        smiles[i] = lv_arc_create(screen);
        lv_obj_remove_style_all(smiles[i]);
        lv_obj_set_size(smiles[i], 36, 32);
        lv_obj_set_style_arc_color(smiles[i], lv_color_hex(0x1A1412), LV_PART_INDICATOR);
        lv_obj_set_style_arc_width(smiles[i], 7, LV_PART_INDICATOR);
        lv_obj_set_style_arc_rounded(smiles[i], true, LV_PART_INDICATOR);
        lv_obj_set_style_arc_opa(smiles[i], LV_OPA_TRANSP, LV_PART_MAIN);
        lv_arc_set_bg_angles(smiles[i], 0, 360);
        lv_arc_set_angles(smiles[i], 200, 340);
        lv_obj_remove_flag(smiles[i], LV_OBJ_FLAG_CLICKABLE);
        lv_obj_add_flag(smiles[i], LV_OBJ_FLAG_HIDDEN);
    }
    for (int i=0;i<24;i++) {
        flying[i]=lv_image_create(screen);
        lv_image_set_src(flying[i],&heart_image);
        lv_obj_remove_flag(flying[i],LV_OBJ_FLAG_CLICKABLE);
        lv_obj_add_flag(flying[i],LV_OBJ_FLAG_HIDDEN);
        sleep_z[i]=lv_label_create(screen);
        lv_label_set_text(sleep_z[i],"z");
        lv_obj_set_style_text_font(sleep_z[i],&mochi_font_20,0);
        lv_obj_set_style_text_color(sleep_z[i],lv_color_hex(0xD1DBEB),0);
        lv_obj_remove_flag(sleep_z[i],LV_OBJ_FLAG_CLICKABLE);
        lv_obj_add_flag(sleep_z[i],LV_OBJ_FLAG_HIDDEN);
    }

    mouth=oval(screen,18,4,0x1A1412);show(mouth,false);
    hat_front=lv_image_create(screen);lv_obj_remove_flag(hat_front,LV_OBJ_FLAG_CLICKABLE);
    lv_image_set_antialias(hat_front,false);lv_image_set_antialias(hat_back,false);
    badge=oval(screen,36,36,0x3B9DF5);show(badge,false);
    badge_text=lv_label_create(badge);lv_obj_set_style_text_font(badge_text,&mochi_font_16,0);
    lv_obj_set_style_text_color(badge_text,lv_color_white(),0);
    for(int i=0;i<3;i++)badge_dots[i]=oval(badge,4,4,0xFFFFFF);
    for(int i=0;i<24;i++){lv_obj_move_foreground(flying[i]);lv_obj_move_foreground(sleep_z[i]);}
    coucou_motion_init(&motion,esp_timer_get_time()/1000000.0,esp_random());
    created=true;active=find_clip("idle");apply_appearance();
    if(pose_source_lock && pose_jobs)xTaskCreatePinnedToCore(pose_worker,"mochi_pose",4096,NULL,3,&pose_task,0);
    return true;
}
void mochi_animation_personalize(lv_obj_t *parent)
{
    if(!created)return;
    bool next=parent!=NULL;
    if(next==wardrobe_view)return;
    wardrobe_view=next;last_draw=0;speech_frozen=false;
    atomic_fetch_add(&pose_generation,1);body_was_transformed=false;retire_body_pose(body);
    body_pose.ready=false;
    lv_obj_set_parent(scene,parent?parent:scene_home);
    lv_obj_set_pos(scene,next?65:0,next?94:0);
    lv_obj_set_size(scene,next?336:466,next?176:466);
    lv_obj_move_background(scene);
    if(next)mochi_animation_state(MOCHI_IDLE);
    lv_timer_ready(animation_timer);
}
void mochi_animation_state(mochi_state_t next)
{
    if(!created)return;
    state=next;preview=false;preview_outfit=-1;
    motion.now=esp_timer_get_time()/1000000.0;
    coucou_motion_state(&motion,motion_state(next));motion.dancing=next==MOCHI_DANCING;
    active=find_clip(state_id(next));
    if(next==MOCHI_HAPPY||next==MOCHI_LOVE||next==MOCHI_SURPRISED||next==MOCHI_PROUD||next==MOCHI_WINK||next==MOCHI_YAWN||next==MOCHI_ANNOYED)
        coucou_motion_emote(&motion,state_id(next),1.8f);
    preview_until=active&&!active->loop?esp_timer_get_time()+(int64_t)active->duration_ms*1000:0;
    apply_appearance();
}
int mochi_animation_duration(mochi_state_t next)
{
    const native_clip_t *clip=find_clip(state_id(next));return clip&&!clip->loop?clip->duration_ms:0;
}
void mochi_animation_look(float x,float y)
{
    target_x=x;target_y=y;last_interaction=esp_timer_get_time();
}
bool mochi_animation_play(const char *id)
{
    const native_clip_t *clip=find_clip(id);if(!clip||!created)return false;
    coucou_motion_init(&motion,esp_timer_get_time()/1000000.0,esp_random());
    atomic_fetch_add(&pose_generation,1);body_was_transformed=false;retire_body_pose(body);
    frame_dt_index=frame_dt_count=0;last_draw=0;
    mochi_animation_state(MOCHI_IDLE);active=clip;preview=true;motion.motion_mode=0;
    preview_until=esp_timer_get_time()+(int64_t)(clip->duration_ms+200)*1000;
    if(!strcmp(clip->group,"state"))coucou_motion_state(&motion,motion_state(mochi_state_from_name(id)));
    else if(!strcmp(clip->group,"emote"))coucou_motion_emote(&motion,id,1.8f);
    else if(!strcmp(clip->group,"mini")){
        motion.mini=true;coucou_motion_permanent(&motion,id+5);motion.next_behavior=motion.now+.25;
    } else if(!strcmp(clip->group,"outfit")){
        for(unsigned i=1;i<12;i++)if(!strcmp(id+7,mochi_appearance_outfit_id(i))){preview_outfit=i;select_outfit(i,true);break;}
    } else coucou_motion_gesture(&motion,id);
    return true;
}
const char *mochi_animation_next(int direction)
{
    gallery_index=(gallery_index+CLIP_COUNT+(direction<0?-1:1))%CLIP_COUNT;
    return mochi_animation_play(clips[gallery_index].id)?clips[gallery_index].label:NULL;
}
unsigned mochi_animation_count(void){return CLIP_COUNT;}
const char *mochi_animation_motion_mode(void)
{
    mochi_appearance_t p;mochi_appearance_get(&p);return p.motion==0?"normal":p.motion==1?"calm":"still";
}
bool mochi_animation_motion_set(const char *name)
{
    return !strcmp(name,"normal")?mochi_appearance_set(3,0):!strcmp(name,"calm")?mochi_appearance_set(3,1):!strcmp(name,"still")?mochi_appearance_set(3,2):false;
}
bool mochi_animation_uploading(void){return false;}
void mochi_animation_upload_poll(void){}
static void live_mouth(bool visible)
{
    mochi_output_status_t out;mochi_audio_output_status(&out);
    unsigned pose=out.level_q10<30?0:out.level_q10<110?1:out.level_q10<260?2:3;
    if(!visible||state!=MOCHI_SPEAKING)pose=0;
    static const int widths[]={0,16,22,28},heights[]={0,8,17,26};
    if(pose){
        lv_obj_set_size(mouth,widths[pose],heights[pose]);
        center_at(mouth,speech_frozen?speech_mouth_x:233+motion.value[CQ_OX]*120+motion.value[CQ_YAW]*5,
            speech_frozen?speech_mouth_y:290+motion.value[CQ_OY]*120);
    }
    show(mouth,pose>0);mouth_pose=pose;mouth_tick=(unsigned)xTaskGetTickCount();mouth_sample_age=out.age_ms;
    mouth_level=out.level_q10;mouth_sequence=out.sequence;
}
void mochi_animation_tick(bool visible)
{
    if(!created)return;
    live_mouth(visible);
    if(!visible){last_draw=0;return;}
    int64_t now=esp_timer_get_time();
    if(preview_until && now>=preview_until){mochi_set_state(MOCHI_IDLE,0);return;}
    if(appearance_seen!=mochi_appearance_revision())apply_appearance();
    if(state==MOCHI_SPEAKING && speech_frozen){
        /* A large costume redraw can occupy the GUI for several DMA buffers.
         * Hold that pose during speech, while the mouth and original blinking
         * continue in small dirty regions at the live audio cadence. */
        coucou_motion_step(&motion,now/1000000.0);
        for(int i=0;i<2;i++)if(speech_eyes[i].active){
            speech_eye_t *eye=&speech_eyes[i];
            lv_obj_set_size(eyes[i],fmaxf(1,eye->width),
                fmaxf(1,fmaxf(eye->height*motion.value[CQ_OPEN],eye->min_height)));
            center_at(eyes[i],eye->x,eye->y);
        }
        last_draw=now;
        return;
    }
    if(now-last_draw<15000 && atomic_load(&pose_ready)<0)return;
    if(last_draw){frame_dt[frame_dt_index++%64]=(unsigned)(now-last_draw);if(frame_dt_count<64)frame_dt_count++;}
    last_draw=now;
    if(preview && preview_outfit>=0 && now>preview_until-900000 && motion.value[CQ_OUTFIT]>.99f)coucou_motion_outfit(&motion,false);
    render_native(NULL);
    speech_frozen=state==MOCHI_SPEAKING;
    render_us=(unsigned)(esp_timer_get_time()-now);
}
void mochi_animation_bind_timer(lv_timer_t *timer){animation_timer=timer;}
unsigned mochi_animation_cleanup_storage(void)
{
    DIR *directory=opendir("/mochi");if(!directory)return 0;
    unsigned count=0;struct dirent *entry;
    while((entry=readdir(directory))){
        vTaskDelay(pdMS_TO_TICKS(5));const char *name=entry->d_name;
        if(strlen(name)!=21||(name[0]!='c'&&name[0]!='t')||strspn(name+1,"0123456789abcdef")!=16||strcmp(name+17,".gif"))continue;
        char filename[40];snprintf(filename,sizeof(filename),"/mochi/%.21s",name);if(!remove(filename))count++;
    }
    closedir(directory);return count;
}
static void describe_native(char *line,size_t size)
{
    unsigned worst=0,total=0;
    for(unsigned i=0;i<frame_dt_count;i++){total+=frame_dt[i];if(frame_dt[i]>worst)worst=frame_dt[i];}
    snprintf(line,size,"@animation character=Mochi hardware=1.75-G renderer=native loaded=%d animation=%s frame=%u motion=%s uploading=0 count=%u scale=256 mean_us=%u max_us=%u render_us=%u mask_fast=%d body_frames=%u worker=%d\n",created,active?active->id:"idle",frames,mochi_animation_motion_mode(),(unsigned)CLIP_COUNT,frame_dt_count?total/frame_dt_count:0,worst,render_us,body_mask_ready,async_presented,pose_task!=NULL);
}
bool mochi_animation_console(const char *command)
{
    if(!strcmp(command,"@native-view")){
        if(esp_lv_adapter_lock(1000)==ESP_OK){
            printf("@mochi_native_view wardrobe=%d visible=%d x=%ld y=%ld w=%ld h=%ld scroll_x=%ld scroll_y=%ld parent_scroll_x=%ld parent_scroll_y=%ld body_x=%ld body_y=%ld body_opa=%u body_visible=%d eyes_x=%ld eyes_y=%ld\n",
                wardrobe_view,lv_obj_is_visible(scene),(long)lv_obj_get_x(scene),(long)lv_obj_get_y(scene),(long)lv_obj_get_width(scene),(long)lv_obj_get_height(scene),
                (long)lv_obj_get_scroll_x(scene),(long)lv_obj_get_scroll_y(scene),
                (long)lv_obj_get_scroll_x(lv_obj_get_parent(scene)),(long)lv_obj_get_scroll_y(lv_obj_get_parent(scene)),
                (long)lv_obj_get_x(body),(long)lv_obj_get_y(body),lv_obj_get_style_image_opa(body,0),lv_obj_is_visible(body),
                (long)lv_obj_get_x(eyes[0]),(long)lv_obj_get_y(eyes[0]));
            esp_lv_adapter_unlock();
        }
    }else if(!strcmp(command,"@animation")){
        char line[320];
        if(esp_lv_adapter_lock(1000)==ESP_OK){describe_native(line,sizeof(line));esp_lv_adapter_unlock();printf("%s",line);}
    }else if(!strncmp(command,"@animation-play ",16)){
        bool ok=false;if(!mochi_voice_busy()&&esp_lv_adapter_lock(1000)==ESP_OK){mochi_set_state(MOCHI_IDLE,0);ok=mochi_animation_play(command+16);esp_lv_adapter_unlock();}
        printf("@animation_play %s\n",ok?"ok":"unavailable");
    }else if(!strncmp(command,"@animation-motion ",18)){
        printf("@animation_motion %s\n",mochi_animation_motion_set(command+18)?"ok":"invalid_or_unsaved");
    }else if(!strcmp(command,"@mochi-av")){
        mochi_output_status_t out;
        if(esp_lv_adapter_lock(1000)==ESP_OK){
            mochi_audio_output_status(&out);
            bool speaking=state==MOCHI_SPEAKING;unsigned pose=mouth_pose,sample_age=mouth_sample_age;
            unsigned sampled_level=mouth_level,sampled_sequence=mouth_sequence;
            unsigned ui_age=(unsigned)pdTICKS_TO_MS((TickType_t)((unsigned)xTaskGetTickCount()-mouth_tick));
            esp_lv_adapter_unlock();
            printf("@mochi_av tap=%d active=%d level=%u mean=%u dma_age_ms=%u sequence=%u speaking=%d pose=%u ui_age_ms=%u sample_age_ms=%u mouth_level=%u mouth_sequence=%u\n",out.tap_ready,out.active,out.level_q10,out.mean_abs,out.age_ms,out.sequence,speaking,pose,ui_age,sample_age,sampled_level,sampled_sequence);
        }
    }else if(!strcmp(command,"@appearance")){
        mochi_appearance_t p;mochi_appearance_get(&p);
        printf("@appearance outfit=%u color=%u expression=%u motion=%u saved=%d\n",p.outfit,p.color,p.expression,p.motion,mochi_appearance_saved());
    }else if(!strncmp(command,"@appearance-set ",16)){
        unsigned field,next;char tail;
        bool ok=sscanf(command+16,"%u %u %c",&field,&next,&tail)==2&&mochi_appearance_set(field,next);
        printf("@appearance_set %s\n",ok?"ok":"invalid");
    }else if(!strcmp(command,"@appearance-reload")){
        mochi_appearance_init();printf("@appearance_reload ok\n");
    }else if(!strcmp(command,"@animation-abort")){
        printf("@animation_upload aborted\n");
    }else return false;
    fflush(stdout);return true;
}
