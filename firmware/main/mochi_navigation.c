/* Native circular-screen navigator. Network/render work never owns LVGL/I2S. */
#include "mochi_navigation.h"
#include "src/misc/cache/instance/lv_image_cache.h"
#include "mochi_runtime.h"
#include "mochi_gps.h"
#include "mochi.h"
#include "mochi_fonts.h"
#include "mochi_display.h"
#include "mochi_controls.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "cJSON.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include <math.h>
#include <limits.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAP_W 384
#define MAP_H 224
#define MAP_BYTES (MAP_W*MAP_H*2)
typedef struct {
    char id[33],phase[24],mode[8],destination[192],instruction[192],message[128],arrow[32],cue[32];
    char candidates[3][192];
    int count,turn,remaining,seconds,revision,sequence,zoom,generation;
    double map_x,map_y;
    bool simulation;
    int64_t received;
} nav_state_t;
static nav_state_t snapshot;
static SemaphoreHandle_t guard;
static atomic_int command;
static atomic_bool shown,show_requested,hide_requested,started,simulating,simulation_lost;
static double simulated_latitude,simulated_longitude;
static char requested_session[33];
static uint8_t *pending_pixels,*display_pixels;
static int pending_revision,display_revision=-1;
static nav_state_t pending_map,display_map;
static int played_sequence;
static lv_obj_t *overlay,*chip,*title,*instruction,*turn,*arrow,*map_image,*marker,*summary,*message;
static lv_obj_t *foot,*car,*destinations[3],*retry,*credit,*credit_panel,*simulation_label;
static lv_image_dsc_t map_descriptor;
static lv_indev_t *diagnostic_pointer;
static lv_point_t diagnostic_point;
static bool diagnostic_pressed;

static bool valid_id(const char *id)
{
    if(!id || strlen(id)!=32) return false;
    for(unsigned i=0;i<32;i++) if(!((id[i]>='0'&&id[i]<='9')||(id[i]>='a'&&id[i]<='f'))) return false;
    return true;
}
bool mochi_navigation_visible(void) { return atomic_load(&shown); }
void mochi_navigation_hide(void) { atomic_store(&hide_requested,true); }
void mochi_navigation_session(const char *id)
{
    if(!guard || !valid_id(id)) return;
    xSemaphoreTake(guard,portMAX_DELAY);
    strlcpy(requested_session,id,sizeof(requested_session));
    xSemaphoreGive(guard);
    atomic_store(&show_requested,true);
}
bool mochi_navigation_simulation(bool enabled,double latitude,double longitude)
{
    if(!guard || !isfinite(latitude) || !isfinite(longitude) || fabs(latitude)>85 || fabs(longitude)>180) return false;
    xSemaphoreTake(guard,portMAX_DELAY);
    simulated_latitude=latitude; simulated_longitude=longitude; atomic_store(&simulating,enabled);
    atomic_store(&simulation_lost,false);
    xSemaphoreGive(guard); return true;
}
void mochi_navigation_simulation_lost(void) { atomic_store(&simulating,true); atomic_store(&simulation_lost,true); }
static void position(mochi_gps_status_t *gps)
{
    mochi_gps_status(gps);
    if(atomic_load(&simulating)) {
        xSemaphoreTake(guard,portMAX_DELAY);
        gps->latitude=simulated_latitude; gps->longitude=simulated_longitude;
        gps->fix=!atomic_load(&simulation_lost); gps->age_seconds=0;
        xSemaphoreGive(guard);
    }
}

static const char *string(cJSON *json,const char *key)
{
    cJSON *item=cJSON_GetObjectItemCaseSensitive(json,key);
    return cJSON_IsString(item)?item->valuestring:"";
}
static double numeric(cJSON *json,const char *key)
{
    cJSON *item=cJSON_GetObjectItemCaseSensitive(json,key);
    return !item?0:cJSON_IsNumber(item)&&isfinite(item->valuedouble)?item->valuedouble:NAN;
}
static bool nonnegative_integer(cJSON *json,const char *key,int *out)
{
    double value=numeric(json,key);
    /* Validate the double before converting: an out-of-range cast is undefined. */
    if(!isfinite(value) || value<0 || value>INT_MAX || trunc(value)!=value) return false;
    *out=(int)value; return true;
}
static bool same_map(const nav_state_t *frame,int revision,const nav_state_t *state)
{
    return revision==state->revision && !strcmp(frame->id,state->id) &&
        frame->generation==state->generation && frame->zoom==state->zoom;
}
static bool parse(const char *body,size_t size,nav_state_t *out)
{
    cJSON *json=cJSON_ParseWithLength(body,size);
    if(!json || !valid_id(string(json,"id"))) { cJSON_Delete(json); return false; }
    memset(out,0,sizeof(*out));
#define COPY(field,key) strlcpy(out->field,string(json,key),sizeof(out->field))
    COPY(id,"id"); COPY(phase,"phase"); COPY(mode,"mode"); COPY(destination,"destination");
    COPY(instruction,"instruction"); COPY(message,"message"); COPY(arrow,"arrow"); COPY(cue,"cue");
#undef COPY
    bool valid=nonnegative_integer(json,"turn_metres",&out->turn) &&
        nonnegative_integer(json,"remaining_metres",&out->remaining) &&
        nonnegative_integer(json,"remaining_seconds",&out->seconds) &&
        nonnegative_integer(json,"map_revision",&out->revision) &&
        nonnegative_integer(json,"cue_seq",&out->sequence) &&
        nonnegative_integer(json,"map_zoom",&out->zoom) &&
        nonnegative_integer(json,"route_generation",&out->generation);
    out->map_x=numeric(json,"map_x"); out->map_y=numeric(json,"map_y");
    out->simulation=cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(json,"simulation"));
    cJSON *array=cJSON_GetObjectItemCaseSensitive(json,"candidates");
    for(int i=0;i<3;i++) {
        cJSON *item=cJSON_GetArrayItem(array,i);
        if(cJSON_IsString(item)) { strlcpy(out->candidates[out->count++],item->valuestring,192); }
    }
    cJSON_Delete(json);
    if(!valid || out->zoom>20 || !isfinite(out->map_x) || !isfinite(out->map_y)) return false;
    out->received=esp_timer_get_time(); return true;
}

typedef struct { uint8_t *data; size_t size,capacity; } buffer_t;
static esp_err_t collect(const uint8_t *bytes,size_t size,void *context)
{
    buffer_t *buffer=context;
    if(mochi_voice_busy() || size>buffer->capacity-buffer->size) return ESP_ERR_INVALID_SIZE;
    memcpy(buffer->data+buffer->size,bytes,size); buffer->size+=size; return ESP_OK;
}
static unsigned word(const uint8_t *p) { return p[0]|((unsigned)p[1]<<8); }
static bool decode(const uint8_t *source,size_t size,uint8_t *pixels)
{
    if(size<10 || memcmp(source,"MMAP",4) || source[4]!=1 || source[5]>1 || word(source+6)!=MAP_W || word(source+8)!=MAP_H) return false;
    if(!source[5]) { if(size!=10+MAP_BYTES) return false; memcpy(pixels,source+10,MAP_BYTES); return true; }
    size_t output=0;
    for(size_t offset=10;offset<size;offset+=4) {
        if(offset+4>size) return false;
        unsigned count=word(source+offset);
        if(!count || output+count*2>MAP_BYTES) return false;
        for(unsigned i=0;i<count;i++) { pixels[output++]=source[offset+2]; pixels[output++]=source[offset+3]; }
    }
    return output==MAP_BYTES;
}

static void worker(void *unused)
{
    (void)unused;
    uint8_t *json=heap_caps_malloc(8192,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    if(!json) { atomic_store(&started,false); vTaskDelete(NULL); return; }
    bool checked=false;
    while(true) {
        vTaskDelay(pdMS_TO_TICKS(2000));
        if(mochi_voice_busy() || mochi_controls_power_pending() || !mochi_runtime_trusted_channel()) continue;
        char id[33]; nav_state_t old;
        xSemaphoreTake(guard,portMAX_DELAY);
        old=snapshot; strlcpy(id,requested_session[0]?requested_session:snapshot.id,sizeof(id));
        bool new_session=requested_session[0] && strcmp(requested_session,snapshot.id);
        xSemaphoreGive(guard);
        if(!id[0] && checked) { vTaskDelay(pdMS_TO_TICKS(8000)); continue; }
        if(id[0] && !new_session && (!strcmp(old.phase,"cancelled") || !strcmp(old.phase,"arrived"))) continue;
        int action=atomic_exchange(&command,0),status=0;
        char route[144],body[512];
        snprintf(route,sizeof(route),id[0]?"/v1/navigation/%s":"/v1/navigation/active",id);
        const char *request=NULL;
        if(id[0]) {
            mochi_gps_status_t gps; position(&gps);
            const char *verb=action==1||action==2?"mode":action>=10&&action<=12?"destination":action==9?"cancel":action==20?"retry":"";
            int count=snprintf(body,sizeof(body),"{\"action\":\"%s\",\"mode\":\"%s\",\"candidate\":%d,\"simulation\":%s",verb,action==1?"foot":action==2?"car":"",action>=10&&action<=12?action-10:0,simulating?"true":"false");
            if(gps.fix && gps.age_seconds>=0 && gps.age_seconds<=10)
                snprintf(body+count,sizeof(body)-count,",\"location\":{\"latitude\":%.7f,\"longitude\":%.7f,\"age_seconds\":%d,\"current\":true}}",gps.latitude,gps.longitude,gps.age_seconds);
            else strlcat(body,"}",sizeof(body));
            request=body;
        }
        buffer_t response={.data=json,.capacity=8191};
        esp_err_t error=mochi_runtime_request(route,request,collect,&response,8191,&status);
        if(!id[0] && status==404) checked=true;
        if(error!=ESP_OK) {
            if(action) { int expected=0; atomic_compare_exchange_strong(&command,&expected,action); }
            continue;
        }
        nav_state_t next;
        if(!parse((char *)json,response.size,&next) || (id[0]&&strcmp(id,next.id))) continue;
        checked=true;
        bool active=strcmp(next.phase,"cancelled") && strcmp(next.phase,"arrived");
        mochi_gps_tracking(active && !atomic_load(&simulating));
        xSemaphoreTake(guard,portMAX_DELAY);
        if(strcmp(snapshot.id,next.id)) {
            played_sequence=0;
            /* A pending frame belongs to the old session, even if both use
             * revision 1. Do not let it suppress the new session's download. */
            free(pending_pixels); pending_pixels=NULL;
        }
        snapshot=next;
        if(!strcmp(requested_session,next.id)) requested_session[0]=0;
        bool fetch=active && next.revision>0 && !same_map(&display_map,display_revision,&next) && !pending_pixels;
        xSemaphoreGive(guard);
        if(!id[0] && active) atomic_store(&show_requested,true);
        if(fetch && !mochi_voice_busy()) {
            uint8_t *encoded=heap_caps_malloc(MAP_BYTES+10,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
            uint8_t *pixels=heap_caps_malloc(MAP_BYTES,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
            if(encoded && pixels) {
                buffer_t frame={.data=encoded,.capacity=MAP_BYTES+10};
                snprintf(route,sizeof(route),"/v1/navigation/%s/map/%d",next.id,next.revision);
                if(mochi_runtime_request(route,NULL,collect,&frame,frame.capacity,&status)==ESP_OK && decode(encoded,frame.size,pixels)) {
                    xSemaphoreTake(guard,portMAX_DELAY);
                    if(!pending_pixels && !strcmp(snapshot.id,next.id)) { pending_pixels=pixels; pending_revision=next.revision; pending_map=next; pixels=NULL; }
                    xSemaphoreGive(guard);
                }
            }
            free(pixels); free(encoded);
        }
    }
}

static void hide(lv_obj_t *object,bool hidden)
{
    if(hidden) lv_obj_add_flag(object,LV_OBJ_FLAG_HIDDEN); else lv_obj_remove_flag(object,LV_OBJ_FLAG_HIDDEN);
}
static void action_event(lv_event_t *event)
{
    int action=(intptr_t)lv_event_get_user_data(event);
    mochi_display_activity();
    if(action==30) { atomic_store(&show_requested,true); return; }
    if(action==31) { hide(credit_panel,true); return; }
    if(action==32) { hide(credit_panel,false); lv_obj_move_foreground(credit_panel); return; }
    if(action==8) { mochi_navigation_hide(); return; }
    if(action==9) { mochi_gps_tracking(false); mochi_navigation_hide(); }
    atomic_store(&command,action);
    if(action!=9) lv_label_set_text(message,"Calculando…");
}
static lv_obj_t *label(lv_obj_t *parent,const char *text,int x,int y,int width,const lv_font_t *font)
{
    lv_obj_t *object=lv_label_create(parent); lv_obj_set_pos(object,x,y); lv_obj_set_width(object,width);
    lv_obj_set_style_text_font(object,font,0); lv_obj_set_style_text_color(object,lv_color_hex(0xf3f1f7),0);
    lv_obj_set_style_text_align(object,LV_TEXT_ALIGN_CENTER,0); lv_label_set_text(object,text);
    lv_obj_remove_flag(object,LV_OBJ_FLAG_CLICKABLE); return object;
}
static lv_obj_t *button(lv_obj_t *parent,const char *text,int x,int y,int width,int height,int action)
{
    lv_obj_t *object=lv_button_create(parent); lv_obj_set_pos(object,x,y); lv_obj_set_size(object,width,height);
    lv_obj_set_style_bg_color(object,lv_color_hex(0x232631),0); lv_obj_set_style_radius(object,16,0);
    lv_obj_set_style_border_width(object,0,0); lv_obj_set_style_shadow_width(object,0,0);
    lv_obj_set_style_pad_all(object,5,0); lv_obj_remove_flag(object,LV_OBJ_FLAG_SCROLLABLE|LV_OBJ_FLAG_GESTURE_BUBBLE);
    lv_obj_add_event_cb(object,action_event,LV_EVENT_CLICKED,(void *)(intptr_t)action);
    lv_obj_t *text_label=label(object,text,0,0,width-12,&mochi_font_16); lv_obj_center(text_label);
    return object;
}
static void map_touch(lv_event_t *event)
{
    lv_event_code_t code=lv_event_get_code(event);
    if(code==LV_EVENT_LONG_PRESSED) mochi_voice_start();
    if(code==LV_EVENT_RELEASED || code==LV_EVENT_PRESS_LOST) mochi_voice_stop();
}
static void tick(lv_timer_t *timer)
{
    (void)timer;
    if(!guard || xSemaphoreTake(guard,0)!=pdTRUE) return;
    nav_state_t state=snapshot;
    bool session_requested=requested_session[0]!=0;
    bool new_frame=pending_pixels!=NULL;
    if(new_frame) {
        lv_image_cache_drop(&map_descriptor);
        uint8_t *previous=display_pixels; display_pixels=pending_pixels; pending_pixels=NULL;
        display_revision=pending_revision;
        display_map=pending_map;
        map_descriptor=(lv_image_dsc_t){.header={.magic=LV_IMAGE_HEADER_MAGIC,.cf=LV_COLOR_FORMAT_RGB565,
            .w=MAP_W,.h=MAP_H,.stride=MAP_W*2},.data_size=MAP_BYTES,.data=display_pixels};
        lv_image_set_src(map_image,&map_descriptor); free(previous);
    }
    xSemaphoreGive(guard);
    if(atomic_exchange(&hide_requested,false)) { atomic_store(&shown,false); hide(overlay,true); }
    if(atomic_exchange(&show_requested,false)) {
        mochi_settings_set_open(false); atomic_store(&shown,true); hide(overlay,false); lv_obj_move_foreground(overlay);
    }
    bool active=state.id[0] && strcmp(state.phase,"cancelled");
    if(!active && !atomic_load(&show_requested) && !session_requested) { atomic_store(&shown,false); hide(overlay,true); }
    hide(chip,!active || shown || mochi_interaction_blocked());
    if(!shown) return;
    hide(simulation_label,!state.simulation && !atomic_load(&simulating));
    mochi_display_activity();
    bool choosing=!strcmp(state.phase,"choose_mode"),selecting=!strcmp(state.phase,"choose_destination");
    bool guiding=!strcmp(state.phase,"guiding") || !strcmp(state.phase,"off_route") || !strcmp(state.phase,"arrived");
    bool stale=esp_timer_get_time()-state.received>10000000;
    hide(foot,!choosing); hide(car,!choosing);
    for(int i=0;i<3;i++) { hide(destinations[i],!selecting || i>=state.count);
        if(selecting && i<state.count) lv_label_set_text(lv_obj_get_child(destinations[i],0),state.candidates[i]); }
    lv_label_set_text(title,!state.id[0]?"Preparando ruta…":choosing?"¿Cómo vas a ir?":selecting?"Elige el destino":state.destination);
    hide(turn,!guiding); hide(arrow,!guiding); hide(instruction,!guiding); hide(summary,!guiding);
    hide(retry,strcmp(state.phase,"unavailable")!=0);
    bool map_ready=display_pixels && !strcmp(display_map.id,state.id) && display_map.generation==state.generation && display_map.zoom==state.zoom;
    hide(map_image,!map_ready || choosing || selecting);
    hide(credit,!map_ready || choosing || selecting);
    char text[128];
    if(guiding) {
        if(state.turn>=1000) snprintf(text,sizeof(text),"%.1f km",state.turn/1000.f); else snprintf(text,sizeof(text),"%d m",state.turn);
        lv_label_set_text(turn,text);
        const char *symbol=strstr(state.arrow,"left")?LV_SYMBOL_LEFT:strstr(state.arrow,"right")?LV_SYMBOL_RIGHT:
            !strcmp(state.arrow,"arrive")?LV_SYMBOL_OK:!strcmp(state.arrow,"uturn")?LV_SYMBOL_LOOP:LV_SYMBOL_UP;
        lv_label_set_text(arrow,symbol);
        lv_label_set_text(instruction,state.instruction);
        snprintf(text,sizeof(text),state.remaining>=1000?"%.1f km · %d min":"%.0f m · %d min",
                 state.remaining>=1000?state.remaining/1000.f:(float)state.remaining,state.seconds/60+(state.seconds%60!=0));
        lv_label_set_text(summary,text);
    }
    mochi_gps_status_t gps; position(&gps);
    const char *notice=choosing||selecting?"":stale?"Sin conexión · guía en pausa":guiding && !gps.fix?"GPS perdido · guía en pausa":state.message;
    if(mochi_voice_recording()) notice="Te escucho…";
    if(!map_ready && guiding && !notice[0]) notice="Cargando mapa…";
    lv_label_set_text(message,notice); hide(message,!notice[0]);
    bool live=guiding && !stale && !strcmp(state.phase,"guiding") && gps.fix && gps.age_seconds>=0 && gps.age_seconds<=10 && map_ready;
    if(live) {
        double size=256.*(1u<<display_map.zoom),lat=gps.latitude*0.017453292519943295;
        double x=(gps.longitude+180)/360.*size-display_map.map_x;
        double y=(1-asinh(tan(lat))/3.141592653589793)/2*size-display_map.map_y;
        if(x>=8 && x<MAP_W-8 && y>=8 && y<MAP_H-8) lv_obj_set_pos(marker,41+(int)x-8,142+(int)y-8);
        else live=false;
    }
    hide(marker,!live);
}

void mochi_navigation_create(lv_obj_t *screen)
{
    guard=xSemaphoreCreateMutex(); if(!guard) return;
    overlay=lv_obj_create(screen); lv_obj_remove_style_all(overlay); lv_obj_set_size(overlay,466,466);
    lv_obj_set_style_bg_color(overlay,lv_color_black(),0); lv_obj_set_style_bg_opa(overlay,LV_OPA_COVER,0);
    lv_obj_remove_flag(overlay,LV_OBJ_FLAG_SCROLLABLE|LV_OBJ_FLAG_GESTURE_BUBBLE);
    lv_obj_add_event_cb(overlay,map_touch,LV_EVENT_ALL,NULL);
    simulation_label=label(overlay,"SIMULACIÓN",158,14,150,&mochi_font_14);
    lv_obj_set_style_text_color(simulation_label,lv_color_hex(0xffce73),0); hide(simulation_label,true);
    title=label(overlay,"Preparando ruta…",83,80,300,&mochi_font_16); lv_label_set_long_mode(title,LV_LABEL_LONG_DOT);
    lv_obj_set_height(title,21);
    arrow=label(overlay,LV_SYMBOL_UP,100,35,70,&lv_font_montserrat_28);
    turn=label(overlay,"",175,35,170,&lv_font_montserrat_28);
    instruction=label(overlay,"",74,101,318,&mochi_font_16); lv_obj_set_height(instruction,40); lv_label_set_long_mode(instruction,LV_LABEL_LONG_DOT);
    map_image=lv_image_create(overlay); lv_obj_set_pos(map_image,41,142); lv_obj_add_flag(map_image,LV_OBJ_FLAG_EVENT_BUBBLE);
    marker=lv_obj_create(overlay); lv_obj_remove_style_all(marker); lv_obj_set_size(marker,16,16);
    lv_obj_set_style_radius(marker,LV_RADIUS_CIRCLE,0); lv_obj_set_style_bg_color(marker,lv_color_hex(0x1769e8),0);
    lv_obj_set_style_bg_opa(marker,LV_OPA_COVER,0); lv_obj_set_style_border_width(marker,3,0);
    lv_obj_set_style_border_color(marker,lv_color_white(),0); lv_obj_remove_flag(marker,LV_OBJ_FLAG_CLICKABLE);
    credit=button(overlay,"© OpenStreetMap contributors",65,343,336,23,32);
    lv_obj_set_style_bg_opa(credit,LV_OPA_80,0);
    lv_obj_set_style_text_font(lv_obj_get_child(credit,0),&mochi_font_14,0);
    summary=label(overlay,"",100,374,266,&mochi_font_16);
    message=label(overlay,"",83,235,300,&mochi_font_16);
    lv_obj_set_style_bg_color(message,lv_color_black(),0); lv_obj_set_style_bg_opa(message,LV_OPA_80,0);
    foot=button(overlay,"A pie",82,192,140,64,1); car=button(overlay,"En coche",244,192,140,64,2);
    for(int i=0;i<3;i++) destinations[i]=button(overlay,"",68,157+i*60,330,54,10+i);
    retry=button(overlay,"Reintentar",153,295,160,48,20);
    button(overlay,"Mochi",113,401,112,40,8); button(overlay,"Terminar",241,401,112,40,9);
    credit_panel=lv_obj_create(overlay); lv_obj_set_pos(credit_panel,60,125); lv_obj_set_size(credit_panel,346,230);
    lv_obj_set_style_bg_color(credit_panel,lv_color_hex(0x111318),0); lv_obj_remove_flag(credit_panel,LV_OBJ_FLAG_SCROLLABLE);
    label(credit_panel,"© OpenStreetMap contributors\nDatos: ODbL · Rutas: OSRM\nCorregir el mapa:\nopenstreetmap.org/fixthemap",8,10,300,&mochi_font_14);
    button(credit_panel,"Volver",85,155,140,42,31); hide(credit_panel,true);
    chip=button(screen,"Volver al mapa",153,385,160,40,30); hide(chip,true); hide(overlay,true);
    lv_timer_create(tick,250,NULL);
}
void mochi_navigation_start(void)
{
    if(guard && !atomic_exchange(&started,true) &&
       xTaskCreatePinnedToCore(worker,"mochi_nav",8192,NULL,1,NULL,0)!=pdPASS) atomic_store(&started,false);
}
bool mochi_navigation_audio(char *route,size_t route_size,char *body,size_t body_size)
{
    if(!guard || atomic_load(&command)==9 || xSemaphoreTake(guard,0)!=pdTRUE) return false;
    nav_state_t state=snapshot;
    bool ready=(!strcmp(state.phase,"guiding")||!strcmp(state.phase,"arrived")) && state.cue[0] &&
        state.sequence>played_sequence && esp_timer_get_time()-state.received<5000000;
    mochi_gps_status_t gps; mochi_gps_status(&gps);
    /* Already holding guard: do not call position(), which also takes it. */
    if(atomic_load(&simulating)) { gps.fix=!atomic_load(&simulation_lost); gps.age_seconds=0; }
    ready=ready && gps.fix && gps.age_seconds>=0 && gps.age_seconds<=10 && !mochi_controls_power_pending();
    if(ready) {
        played_sequence=state.sequence;
        snprintf(route,route_size,"/v1/navigation/%s/audio",state.id);
        snprintf(body,body_size,"{\"sequence\":%d,\"cue\":\"%s\"}",state.sequence,state.cue);
    }
    xSemaphoreGive(guard); return ready;
}
static void read_pointer(lv_indev_t *input,lv_indev_data_t *data)
{
    (void)input; data->point=diagnostic_point;
    data->state=diagnostic_pressed?LV_INDEV_STATE_PRESSED:LV_INDEV_STATE_RELEASED;
}
bool mochi_navigation_pointer(int x,int y,bool pressed)
{
    if(x==-1 && y==-1 && !pressed) {
        if(diagnostic_pointer) lv_indev_delete(diagnostic_pointer);
        diagnostic_pointer=NULL; diagnostic_pressed=false; return true;
    }
    if(!overlay || (!shown && lv_obj_has_flag(chip,LV_OBJ_FLAG_HIDDEN)) || x<0 || y<0 || x>=466 || y>=466) return false;
    if(!diagnostic_pointer) {
        diagnostic_pointer=lv_indev_create(); if(!diagnostic_pointer) return false;
        lv_indev_set_type(diagnostic_pointer,LV_INDEV_TYPE_POINTER);
        lv_indev_set_display(diagnostic_pointer,lv_obj_get_display(overlay));
        lv_indev_set_read_cb(diagnostic_pointer,read_pointer);
    }
    diagnostic_point=(lv_point_t){x,y}; diagnostic_pressed=pressed;
    lv_timer_ready(lv_indev_get_read_timer(diagnostic_pointer)); return true;
}
void mochi_navigation_diagnose(void)
{
    if(!guard) return;
    xSemaphoreTake(guard,portMAX_DELAY);
    printf("@mochi_navigation visible=%d phase=%s mode=%s map=%d cue=%d\n",(int)shown,snapshot.phase,snapshot.mode,display_revision,snapshot.sequence);
    xSemaphoreGive(guard); fflush(stdout);
}
bool mochi_navigation_test(void)
{
    uint8_t *output=heap_caps_malloc(MAP_BYTES,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    if(!output) return false;
    const uint8_t packed[]={ 'M','M','A','P',1,1,128,1,224,0,255,255,31,0,1,80,31,0 };
    bool ok=valid_id("0123456789abcdef0123456789abcdef") && !valid_id("not-an-id") &&
        decode(packed,sizeof(packed),output) && output[0]==31 && output[MAP_BYTES-1]==0 &&
        !decode(packed,sizeof(packed)-1,output);
    free(output);
    nav_state_t first={.id="0123456789abcdef0123456789abcdef",.revision=1,.zoom=17,.generation=1},next=first;
    ok=ok && same_map(&first,1,&next) && !same_map(&first,2,&next);
    next.id[0]='f'; ok=ok && !same_map(&first,1,&next); next=first;
    next.generation++; ok=ok && !same_map(&first,1,&next); next=first;
    next.zoom--; ok=ok && !same_map(&first,1,&next);
    char body[160];
    const char *invalid[]={"-1","1.5","2147483648","1e400","\"1\"","null"};
    for(unsigned i=0;i<sizeof(invalid)/sizeof(invalid[0]);i++) {
        int count=snprintf(body,sizeof(body),"{\"id\":\"%s\",\"map_revision\":%s}",first.id,invalid[i]);
        ok=ok && count>0 && count<sizeof(body) && !parse(body,count,&next);
    }
    static const char valid[]="{\"id\":\"0123456789abcdef0123456789abcdef\",\"map_revision\":1,\"map_zoom\":17}";
    return ok && parse(valid,sizeof(valid)-1,&next) && next.revision==1 && next.zoom==17;
}
