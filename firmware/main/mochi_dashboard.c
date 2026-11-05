#include "mochi_fonts.h"
#include "mochi_education.h"
#include "mochi_dashboard.h"
#include "mochi.h"
#include "mochi_animation.h"
#include "mochi_appearance.h"
#include "mochi_runtime.h"
#include "mochi_options.h"
#include "mochi_controls.h"
#include "mochi_display.h"
#include "mochi_resources.h"
#include "mochi_gps.h"
#include "mochi_wifi_ui.h"
#include "esp_timer.h"
#include <stdatomic.h>
#include <stdio.h>
#include <string.h>

#define TEXT 0xF3F1F7
#define MUTED 0xB4B7C4
#define SURFACE 0x232631
/* Keep the existing diagnostic page IDs. Retired pages return to settings. */
enum { ROOT=0, VOICE=2, ENERGY=3, NAME=5, DEEP_CONFIRM=8, ANIMATIONS=9 };
static lv_obj_t *overlay,*detail,*footer,*editor,*keys,*test_button,*update_button;
static atomic_bool opened;
static unsigned page;
static int64_t updated;
static unsigned wardrobe_field,wardrobe_seen;
static lv_obj_t *wardrobe_tabs[4],*wardrobe_value,*wardrobe_help;
/* Private USB pointer, processed by LVGL exactly like a physical drag. */
static lv_indev_t *diagnostic_pointer;
static lv_point_t diagnostic_point;
static bool diagnostic_pressed;
static lv_point_t wardrobe_drag_start;
static bool wardrobe_dragging;
static void show_page(unsigned next);
static void refresh_wardrobe(void);

static lv_obj_t *label(const char *value,int x,int y,int width,const lv_font_t *font,uint32_t color)
{
    lv_obj_t *o=lv_label_create(overlay); lv_label_set_text(o,value); lv_obj_set_pos(o,x,y);
    lv_obj_set_width(o,width); lv_obj_set_style_text_font(o,font,0); lv_obj_set_style_text_color(o,lv_color_hex(color),0);
    lv_obj_set_style_text_align(o,LV_TEXT_ALIGN_CENTER,0); return o;
}
static void action(lv_event_t *event);
static lv_obj_t *button(const char *value,int x,int y,int width,int height,unsigned id)
{
    lv_obj_t *o=lv_button_create(overlay); lv_obj_set_pos(o,x,y); lv_obj_set_size(o,width,height);
    lv_obj_set_style_bg_color(o,lv_color_hex(SURFACE),0); lv_obj_set_style_radius(o,14,0);
    lv_obj_set_style_shadow_width(o,0,0); lv_obj_set_style_border_width(o,0,0);
    lv_obj_set_style_text_font(o,&mochi_font_16,0); lv_obj_set_style_text_color(o,lv_color_hex(TEXT),0);
    lv_obj_t *text=lv_label_create(o); lv_label_set_text(text,value); lv_obj_center(text);
    lv_obj_add_event_cb(o,action,LV_EVENT_CLICKED,(void *)(uintptr_t)id); return o;
}
void mochi_dashboard_close(void)
{
    mochi_animation_personalize(NULL);
    opened=false; lv_obj_add_flag(overlay,LV_OBJ_FLAG_HIDDEN); mochi_display_activity();
}
bool mochi_dashboard_is_open(void) { return atomic_load(&opened); }
bool mochi_dashboard_preview_active(void){return atomic_load(&opened) && page==ANIMATIONS;}
static void read_diagnostic_pointer(lv_indev_t *input,lv_indev_data_t *data)
{
    (void)input;data->point=diagnostic_point;
    data->state=diagnostic_pressed?LV_INDEV_STATE_PRESSED:LV_INDEV_STATE_RELEASED;
}
bool mochi_dashboard_pointer(int x,int y,bool pressed)
{
    if(x==-1 && y==-1 && !pressed){
        if(diagnostic_pointer)lv_indev_delete(diagnostic_pointer);
        diagnostic_pointer=NULL;diagnostic_pressed=false;return true;
    }
    if(!mochi_dashboard_preview_active() || x<0 || y<0 || x>=466 || y>=466)return false;
    if(!diagnostic_pointer){
        diagnostic_pointer=lv_indev_create();
        if(!diagnostic_pointer)return false;
        lv_indev_set_type(diagnostic_pointer,LV_INDEV_TYPE_POINTER);
        lv_indev_set_display(diagnostic_pointer,lv_obj_get_display(overlay));
        lv_indev_set_read_cb(diagnostic_pointer,read_diagnostic_pointer);
    }
    diagnostic_point=(lv_point_t){x,y};diagnostic_pressed=pressed;
    lv_timer_ready(lv_indev_get_read_timer(diagnostic_pointer));return true;
}
void mochi_dashboard_diagnose(void)
{
    printf("@mochi_personalize active=%d field=%u preview=%d fonts_missing=%u\n",
        mochi_dashboard_preview_active(),wardrobe_field,mochi_dashboard_preview_active(),mochi_fonts_missing());
}
void mochi_dashboard_open(void)
{
    if(mochi_education_active()){mochi_education_options();return;}
    mochi_voice_cancel(); mochi_display_activity(); opened=true; show_page(ROOT);
    lv_obj_remove_flag(overlay,LV_OBJ_FLAG_HIDDEN); lv_obj_move_foreground(overlay);
}
void mochi_dashboard_show(unsigned value)
{
    mochi_dashboard_open(); show_page(value<=ANIMATIONS?value:ROOT);
}
static void name_ready(lv_event_t *event)
{
    (void)event;
    const char *value=lv_textarea_get_text(editor);
    if (!value[0] || !mochi_resources_prepare_name(value)) {
        lv_label_set_text(detail,"Espera a terminar la preparacion actual"); return;
    }
    show_page(VOICE);
}
static void text_activity(lv_event_t *event) { (void)event; mochi_display_activity(); }
static void wardrobe_change(int direction)
{
    mochi_display_activity();mochi_appearance_cycle(wardrobe_field,direction);refresh_wardrobe();
}
static void wardrobe_gesture(lv_event_t *event)
{
    lv_indev_t *input=lv_indev_active();
    if(!input)return;
    lv_event_code_t code=lv_event_get_code(event);
    if(code==LV_EVENT_PRESSED){
        lv_indev_get_point(input,&wardrobe_drag_start);wardrobe_dragging=true;
        mochi_display_activity();
    }else if(code==LV_EVENT_RELEASED && wardrobe_dragging){
        lv_point_t end;lv_indev_get_point(input,&end);wardrobe_dragging=false;
        int dx=end.x-wardrobe_drag_start.x,dy=end.y-wardrobe_drag_start.y;
        if(LV_ABS(dx)>=40 && LV_ABS(dx)>LV_ABS(dy)*1.3f)wardrobe_change(dx<0?1:-1);
    }else if(code==LV_EVENT_PRESS_LOST){
        wardrobe_dragging=false;
    }
}
static void refresh_wardrobe(void)
{
    mochi_appearance_t p;mochi_appearance_get(&p);
    const unsigned values[]={p.outfit,p.color,p.expression,p.motion},counts[]={12,6,8,3};
    const char *hints[]={"Desliza para cambiar la ropa","Desliza para cambiar el color","Desliza para cambiar la expresión","Desliza para cambiar el movimiento"};
    lv_label_set_text(wardrobe_value,mochi_appearance_label(wardrobe_field));
    lv_label_set_text(wardrobe_help,hints[wardrobe_field]);
    for(unsigned i=0;i<4;i++)lv_obj_set_style_bg_color(wardrobe_tabs[i],lv_color_hex(i==wardrobe_field?0x584568:SURFACE),0);
    lv_label_set_text_fmt(footer,"%u / %u · %s",values[wardrobe_field]+1,counts[wardrobe_field],
        mochi_appearance_saved()?"Guardado":"Guardando…");
    wardrobe_seen=mochi_appearance_revision();
}
static void action(lv_event_t *event)
{
    unsigned id=(uintptr_t)lv_event_get_user_data(event); mochi_display_activity();
    mochi_options_t options; mochi_options_get(&options);
    if (id==100) { mochi_dashboard_close(); return; }
    if (id==119) { mochi_dashboard_close(); mochi_education_enter(); return; }
    if (id==101) { show_page(ROOT); return; }
    if (id==102) { mochi_dashboard_close(); mochi_settings_set_open(true); return; }
    if (id==103) { mochi_dashboard_close(); mochi_settings_set_open(true); mochi_wifi_ui_open(); return; }
    if (id==104) { mochi_voice_cancel(); mochi_options_microphone(!options.microphone); show_page(VOICE); return; }
    if (id==108) { mochi_options_power(options.power_mode==MOCHI_POWER_WALK?MOCHI_POWER_HOME:MOCHI_POWER_WALK); show_page(ENERGY); return; }
    if (id==109) { show_page(DEEP_CONFIRM); return; }
    if (id==110) { mochi_controls_request_deep(); return; }
    if (id==111) { mochi_resources_update(); return; }
    if (id==112) { mochi_dashboard_close(); mochi_resources_test_candidate(); return; }
    if (id==113) { name_ready(event); return; }
    if (id==115) { mochi_gps_request(); lv_label_set_text(detail,"GPS buscando una posicion nueva"); return; }
    if (id==116) { mochi_dashboard_close(); mochi_set_state(MOCHI_IDLE,0); mochi_animation_next(1); return; }
    if (id==117) {
        const char *mode=mochi_animation_motion_mode();
        bool saved=mochi_animation_motion_set(!strcmp(mode,"normal")?"calm":!strcmp(mode,"calm")?"still":"normal");
        show_page(ANIMATIONS);
        if (!saved) lv_label_set_text(detail,"No se pudo guardar. Intentalo otra vez");
        return;
    }
    if ((id>=200 && id<204)||(id>=210 && id<214)) {
        mochi_appearance_cycle(id>=210?id-210:id-200,id>=210?1:-1);
        show_page(ANIMATIONS);return;
    }
    if (id==118) { mochi_dashboard_close();mochi_set_state(MOCHI_IDLE,0);return; }
    if(id==220 || id==221){wardrobe_change(id==220?-1:1);return;}
    if(id>=230 && id<234){wardrobe_field=id-230;refresh_wardrobe();return;}
    if (id<=ANIMATIONS) show_page(id);
}
static void show_page(unsigned next)
{
    if (next!=ROOT && next!=VOICE && next!=ENERGY && next!=NAME && next!=DEEP_CONFIRM && next!=ANIMATIONS) next=ROOT;
    page=next; detail=footer=editor=keys=test_button=update_button=NULL;
    mochi_animation_personalize(NULL);
    lv_obj_clean(overlay);
    if(next==ANIMATIONS)mochi_animation_personalize(overlay);
    button(next==ROOT?LV_SYMBOL_CLOSE:LV_SYMBOL_LEFT,83,next==ANIMATIONS?50:60,46,42,next==ROOT?100:101);
    const char *titles[]={[ROOT]="Ajustes",[VOICE]="Voz",[ENERGY]="Bateria",[NAME]="Nuevo nombre",[DEEP_CONFIRM]="Ahorrar bateria",[ANIMATIONS]="Personalizar"};
    label(titles[next],139,next==ANIMATIONS?58:68,190,&mochi_font_20,TEXT);
    if (next==ROOT) {
        const char *names[]={"Audio y volumen","Wi-Fi","Voz y nombre","Bateria y actualizar","Personalizar Mochi","Aprender con Peluqo"};
        const unsigned ids[]={102,103,VOICE,ENERGY,ANIMATIONS,119};
        for (int i=0;i<6;i++) button(names[i],103,119+i*45,260,40,ids[i]);
        footer=label("",133,414,200,&mochi_font_14,MUTED);
    } else if (next==ANIMATIONS) {
        button(LV_SYMBOL_PLAY,337,50,44,42,116);
        lv_obj_t *swipe=lv_obj_create(overlay);lv_obj_remove_style_all(swipe);
        lv_obj_set_pos(swipe,65,96);lv_obj_set_size(swipe,336,172);
        lv_obj_remove_flag(swipe,LV_OBJ_FLAG_SCROLLABLE|LV_OBJ_FLAG_GESTURE_BUBBLE);
        lv_obj_add_event_cb(swipe,wardrobe_gesture,LV_EVENT_ALL,NULL);
        button(LV_SYMBOL_LEFT,50,170,44,44,220);
        button(LV_SYMBOL_RIGHT,372,170,44,44,221);
        wardrobe_help=label("",78,272,310,&mochi_font_14,MUTED);
        const char *tabs[]={"Ropa","Color","Cara","Mover"};
        for(unsigned i=0;i<4;i++){
            wardrobe_tabs[i]=button(tabs[i],76+i*80,300,74,40,230+i);
            lv_obj_set_style_text_font(wardrobe_tabs[i],&mochi_font_14,0);
        }
        button(LV_SYMBOL_LEFT,92,348,42,42,220);
        wardrobe_value=label("",141,353,184,&mochi_font_16,TEXT);
        button(LV_SYMBOL_RIGHT,332,348,42,42,221);
        footer=label("",113,394,240,&mochi_font_14,MUTED);
        button("Listo",163,418,140,36,118);
        refresh_wardrobe();
    } else if (next==VOICE) {
        detail=label("",94,113,278,&mochi_font_16,TEXT);
        mochi_options_t o; mochi_options_get(&o);
        button(o.microphone?"Desactivar microfono":"Activar microfono",103,224,260,46,104);
        button("Preparar otro nombre",103,280,260,46,NAME);
        mochi_resource_status_t s; mochi_resources_status(&s);
        test_button=button("Probar nuevo nombre",103,336,260,46,112);
        if (!s.candidate) lv_obj_add_state(test_button,LV_STATE_DISABLED);
        footer=label("",113,389,240,&mochi_font_14,MUTED);
        lv_obj_set_height(footer,40); lv_label_set_long_mode(footer,LV_LABEL_LONG_MODE_DOTS);
    } else if (next==NAME) {
        detail=label("El anterior seguira activo mientras se prepara",83,102,300,&mochi_font_14,MUTED);
        editor=lv_textarea_create(overlay); lv_obj_set_pos(editor,83,143); lv_obj_set_size(editor,300,44);
        lv_textarea_set_one_line(editor,true); lv_textarea_set_max_length(editor,32);
        lv_obj_add_event_cb(editor,text_activity,LV_EVENT_VALUE_CHANGED,NULL);
        lv_obj_set_style_text_font(editor,&mochi_font_16,0);
        lv_obj_set_style_bg_color(editor,lv_color_hex(SURFACE),0);
        lv_obj_set_style_text_color(editor,lv_color_hex(TEXT),0);
        lv_obj_set_style_border_color(editor,lv_color_hex(MUTED),0);
        button("Preparar nombre",123,195,220,42,113);
        keys=lv_keyboard_create(overlay); lv_obj_set_align(keys,LV_ALIGN_TOP_LEFT);
        lv_obj_set_pos(keys,73,246); lv_obj_set_size(keys,320,150);
        lv_keyboard_set_textarea(keys,editor); lv_keyboard_set_popovers(keys,false);
        lv_obj_set_style_text_font(keys,&mochi_font_14,LV_PART_ITEMS);
        lv_obj_set_style_bg_color(keys,lv_color_hex(SURFACE),LV_PART_ITEMS);
        lv_obj_set_style_text_color(keys,lv_color_hex(TEXT),LV_PART_ITEMS);
        lv_obj_set_style_bg_color(keys,lv_color_black(),0); lv_obj_set_style_bg_opa(keys,LV_OPA_COVER,0);
        lv_obj_add_event_cb(keys,name_ready,LV_EVENT_READY,NULL);
    } else if (next==ENERGY) {
        detail=label("",103,117,260,&mochi_font_14,MUTED);
        mochi_options_t o; mochi_options_get(&o);
        button(o.power_mode==MOCHI_POWER_WALK?"Modo paseo: activo":"Activar modo paseo",103,209,260,44,108);
        button("Ahorro profundo",103,262,260,44,109);
        button("Actualizar ubicacion",103,315,260,44,115);
        update_button=button("Buscar actualizacion",113,369,240,42,111);
    } else if (next==DEEP_CONFIRM) {
        detail=label("Dejare de escuchar mi nombre.\n\nPulsa BOOT para despertar.",103,153,260,&mochi_font_16,TEXT);
        button("Entrar en ahorro",103,270,260,48,110);
        button("Seguir despierto",113,331,240,44,ENERGY);
    }
    updated=0;
}
static void tick(lv_timer_t *timer)
{
    (void)timer;
    if (!opened || !mochi_display_awake()) return;
    int64_t now=esp_timer_get_time();
    if (now-updated<500000) return;
    updated=now;
    char value[360]; mochi_options_t o; mochi_options_get(&o);
    mochi_resource_status_t resources; mochi_resources_status(&resources);
    if(page==ANIMATIONS) {
        if(wardrobe_seen!=mochi_appearance_revision() || !mochi_appearance_saved() || !strstr(lv_label_get_text(footer),"Guardado"))refresh_wardrobe();
    } else if (page==VOICE) {
        if (resources.candidate) lv_obj_remove_state(test_button,LV_STATE_DISABLED);
        else lv_obj_add_state(test_button,LV_STATE_DISABLED);
        snprintf(value,sizeof(value),"Me llamo %s\n\n%s",o.name,o.model_id[0]?(o.microphone?"Di mi nombre para hablar":"Microfono desactivado"):"Reconocimiento aun en preparacion");
        lv_label_set_text(detail,value);
        snprintf(value,sizeof(value),"%s%s",resources.message,o.pending_id[0]?". Sigo con el anterior":""); lv_label_set_text(footer,value);
    } else if (page==ROOT || page==ENERGY) {
        mochi_power_status_t p; mochi_controls_power_status(&p);
        char battery[72];
        if (p.percent>=0) snprintf(battery,sizeof(battery),"Bateria %d%%%s",p.percent,p.charging?" cargando":"");
        else snprintf(battery,sizeof(battery),p.usb?"Alimentacion por USB":"Bateria sin lectura");
        if (page==ROOT) lv_label_set_text(footer,battery);
        else {
            const char *notice=resources.working?resources.message:resources.update_message[0]?resources.update_message:
                "El ahorro profundo desactiva la escucha";
            snprintf(value,sizeof(value),"%s\n%s\n\n%s",battery,o.power_mode==MOCHI_POWER_WALK?"Paseo: escucha con pantalla apagada":"Casa: pantalla activa",notice);
            lv_label_set_text(detail,value);
            if (resources.working) lv_obj_add_state(update_button,LV_STATE_DISABLED);
            else lv_obj_remove_state(update_button,LV_STATE_DISABLED);
        }
    }
}
void mochi_dashboard_create(lv_obj_t *screen)
{
    overlay=lv_obj_create(screen); lv_obj_remove_style_all(overlay); lv_obj_set_pos(overlay,0,0); lv_obj_set_size(overlay,466,466);
    lv_obj_set_style_bg_color(overlay,lv_color_black(),0); lv_obj_set_style_bg_opa(overlay,LV_OPA_COVER,0);
    lv_obj_remove_flag(overlay,LV_OBJ_FLAG_SCROLLABLE); lv_obj_add_flag(overlay,LV_OBJ_FLAG_HIDDEN);
    lv_timer_create(tick,250,NULL);
}
