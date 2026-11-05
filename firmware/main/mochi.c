#include "mochi_fonts.h"
/* Personal hardware adaptation of Coucou's Mochi; see licenses/Coucou-ASSETS.md. */
#include "mochi.h"
#include "mochi_education.h"
#include "mochi_animation.h"
#include "mochi_audio.h"
#include "mochi_controls.h"
#include "mochi_power_ui.h"
#include "mochi_appearance.h"
#include "mochi_gps.h"
#include "mochi_dashboard.h"
#include "mochi_display.h"
#include "mochi_runtime.h"
#include "mochi_navigation.h"
#include "mochi_vpn.h"
#include "mochi_wifi_ui.h"
#include "esp_log.h"
#include "esp_timer.h"
#include <math.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static const char *TAG="mochi_ui";
static lv_obj_t *hint,*dots[3];
static bool sleeping,touch_recording,gesture_click;
static int64_t last_interaction,last_tap,state_until;
static mochi_state_t state=MOCHI_IDLE;
static atomic_uint audio_level_q10;
static void (*voice_start)(void),(*voice_stop)(void);
static bool (*voice_busy)(void);
static lv_obj_t *settings,*volume_slider,*volume_label,*mute_label,*settings_hint;
static atomic_bool settings_open;
static int unmuted_volume=45;
static lv_obj_t *gps_label,*vpn_label;

bool mochi_interaction_blocked(void)
{
    return atomic_load(&settings_open) || mochi_education_blocked() || mochi_dashboard_is_open() || mochi_animation_uploading();
}

static void gps_indicator(lv_timer_t *timer)
{
    (void)timer;
    if (!settings_open || !gps_label) return;
    mochi_gps_status_t gps;
    mochi_gps_status(&gps);
    char text[64];
    if (gps.fix) snprintf(text, sizeof(text), "GPS: listo (%d sat.)", gps.satellites);
    else if (gps.available) snprintf(text, sizeof(text), "GPS: ultima posicion, %d min", gps.age_seconds / 60);
    else snprintf(text, sizeof(text), gps.detected ? "GPS: buscando (%d sat.)" : "GPS: sin respuesta (%d sat.)", gps.satellites);
    if (strcmp(lv_label_get_text(gps_label), text)) lv_label_set_text(gps_label, text);
    if (vpn_label) {
        const char *vpn = mochi_vpn_status_text();
        if (strcmp(lv_label_get_text(vpn_label), vpn)) lv_label_set_text(vpn_label, vpn);
    }
}

static void refresh_volume(void)
{
    int volume = mochi_audio_get_volume();
    if (volume) unmuted_volume = volume;
    lv_slider_set_value(volume_slider, volume, LV_ANIM_OFF);
    lv_label_set_text_fmt(volume_label, "Volumen  %d%%", volume);
    lv_label_set_text(mute_label, volume ? "Silenciar" : "Activar voz");
}

void mochi_settings_set_open(bool open)
{
    if(open && mochi_education_active()){mochi_education_options();return;}
    if (!settings) return;
    settings_open = open;
    if (open) mochi_voice_cancel();
    if (open) {
        refresh_volume();
        gps_indicator(NULL);
        lv_label_set_text(settings_hint, "BOOT: mantener para hablar");
        lv_obj_remove_flag(settings, LV_OBJ_FLAG_HIDDEN);
        lv_obj_move_foreground(settings);
    } else {
        mochi_wifi_ui_close();
        lv_obj_add_flag(settings, LV_OBJ_FLAG_HIDDEN);
    }
    last_interaction = esp_timer_get_time();
    last_tap = 0;
}

static void settings_event(lv_event_t *event)
{
    intptr_t action = (intptr_t)lv_event_get_user_data(event);
    if (action == 1) mochi_dashboard_open();
    else if (action == 2) mochi_settings_set_open(false);
    else if (action == 3) {
        mochi_audio_set_volume(lv_slider_get_value(volume_slider));
        refresh_volume();
    } else if (action == 4 || action == 5) {
        mochi_audio_set_volume(mochi_audio_get_volume() + (action == 4 ? -10 : 10));
        refresh_volume();
    } else if (action == 6) {
        mochi_audio_set_volume(mochi_audio_get_volume() ? 0 : unmuted_volume);
        refresh_volume();
    } else if (action == 7) {
        if (mochi_controls_request_off()) {
            mochi_settings_set_open(false);
            mochi_show_notice("Hasta pronto! Apagando...", 0);
        } else lv_label_set_text(settings_hint, "Espera la respuesta. PWR: 10 s");
    } else if (action == 8) mochi_wifi_ui_open();
}

static lv_obj_t *control_button(lv_obj_t *parent, const char *text, int x, int y, int w, int action)
{
    lv_obj_t *button = lv_button_create(parent);
    lv_obj_set_pos(button, x, y);
    lv_obj_set_size(button, w, 48);
    lv_obj_set_style_bg_color(button, lv_color_hex(0x232631), 0);
    lv_obj_set_style_radius(button, 18, 0);
    lv_obj_set_style_shadow_width(button, 0, 0);
    lv_obj_set_style_text_color(button, lv_color_hex(0xF3F1F7), 0);
    lv_obj_set_style_text_font(button, &mochi_font_16, 0);
    lv_obj_remove_flag(button, LV_OBJ_FLAG_SCROLLABLE | LV_OBJ_FLAG_GESTURE_BUBBLE);
    lv_obj_add_event_cb(button, settings_event, LV_EVENT_CLICKED, (void *)(intptr_t)action);
    lv_obj_t *label = lv_label_create(button);
    lv_label_set_text(label, text);
    lv_obj_center(label);
    return label;
}

static void create_settings(lv_obj_t *screen)
{
    control_button(screen, LV_SYMBOL_SETTINGS, 313, 59, 48, 1);
    settings = lv_obj_create(screen);
    lv_obj_remove_style_all(settings);
    lv_obj_set_size(settings, 466, 466);
    lv_obj_set_style_bg_color(settings, lv_color_black(), 0);
    lv_obj_set_style_bg_opa(settings, LV_OPA_COVER, 0);
    lv_obj_set_style_text_color(settings, lv_color_hex(0xE8E4EF), 0);
    lv_obj_set_style_text_font(settings, &mochi_font_16, 0);
    lv_obj_remove_flag(settings, LV_OBJ_FLAG_SCROLLABLE | LV_OBJ_FLAG_GESTURE_BUBBLE);
    lv_obj_t *title = lv_label_create(settings);
    lv_label_set_text(title, "Ajustes");
    lv_obj_set_style_text_font(title, &mochi_font_20, 0);
    lv_obj_align(title, LV_ALIGN_TOP_MID, -15, 80);
    control_button(settings, LV_SYMBOL_CLOSE, 307, 65, 48, 2);
    volume_label = lv_label_create(settings);
    lv_obj_set_width(volume_label, 250);
    lv_obj_set_style_text_align(volume_label, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_align(volume_label, LV_ALIGN_TOP_MID, 0, 119);
    volume_slider = lv_slider_create(settings);
    lv_obj_set_pos(volume_slider, 111, 165);
    lv_obj_set_size(volume_slider, 244, 10);
    lv_slider_set_range(volume_slider, 0, 100);
    lv_obj_set_style_bg_color(volume_slider, lv_color_hex(0x303441), LV_PART_MAIN);
    lv_obj_set_style_bg_color(volume_slider, lv_color_hex(0xE7ABC8), LV_PART_INDICATOR);
    lv_obj_set_style_bg_color(volume_slider, lv_color_hex(0xF4D8E7), LV_PART_KNOB);
    lv_obj_set_ext_click_area(volume_slider, 18);
    lv_obj_remove_flag(volume_slider, LV_OBJ_FLAG_GESTURE_BUBBLE);
    lv_obj_add_event_cb(volume_slider, settings_event, LV_EVENT_VALUE_CHANGED, (void *)(intptr_t)3);
    control_button(settings, LV_SYMBOL_MINUS, 83, 201, 68, 4);
    mute_label = control_button(settings, "Silenciar", 165, 201, 136, 6);
    control_button(settings, LV_SYMBOL_PLUS, 315, 201, 68, 5);
    control_button(settings, LV_SYMBOL_WIFI "  Wi-Fi", 143, 262, 180, 8);
    lv_obj_t *off_label = control_button(settings, LV_SYMBOL_POWER "  Apagar", 143, 322, 180, 7);
    lv_obj_set_style_bg_color(lv_obj_get_parent(off_label), lv_color_hex(0x412B37), 0);
    settings_hint = lv_label_create(settings);
    lv_obj_set_width(settings_hint, 290);
    lv_obj_set_style_text_font(settings_hint, &mochi_font_14, 0);
    lv_obj_set_style_text_align(settings_hint, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_set_style_text_color(settings_hint, lv_color_hex(0x979AA8), 0);
    lv_obj_align(settings_hint, LV_ALIGN_TOP_MID, 0, 380);
    gps_label = lv_label_create(settings);
    lv_label_set_text(gps_label, "GPS: buscando");
    lv_obj_set_width(gps_label, 250);
    lv_obj_set_style_text_font(gps_label, &mochi_font_14, 0);
    lv_obj_set_style_text_align(gps_label, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_set_style_text_color(gps_label, lv_color_hex(0xB4C2CB), 0);
    lv_obj_align(gps_label, LV_ALIGN_TOP_MID, 0, 402);
    vpn_label = lv_label_create(settings);
    lv_label_set_text(vpn_label, "VPN: sin configurar");
    lv_obj_set_width(vpn_label, 200);
    lv_obj_set_style_text_font(vpn_label, &mochi_font_14, 0);
    lv_obj_set_style_text_align(vpn_label, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_set_style_text_color(vpn_label, lv_color_hex(0xB4C2CB), 0);
    lv_obj_align(vpn_label, LV_ALIGN_TOP_MID, 0, 423);
    lv_timer_create(gps_indicator, 1000, NULL);
    refresh_volume();
    mochi_wifi_ui_create(screen);
    mochi_settings_set_open(false);
}

static const char *state_names[] = {"idle", "happy", "love", "surprised", "sad",
    "sleeping", "thinking", "curious", "proud", "wink", "dizzy", "listening", "speaking", "offline",
    "working", "searching", "approval", "finished", "ratelimit", "yawn", "annoyed", "dancing"};
static const char *state_hints[] = {"Toca o manten pulsado", "Hola, estoy aqui", "Me encanta estar contigo",
    "Oh!", "Estoy contigo", "Z z z", "Estoy pensando", "Cuentame mas", "Lo hemos conseguido",
    "Entre tu y yo", "Que vueltas!", "Te escucho...", "", "Comprueba la conexion",
    "En ello...", "Buscando...", "Lo hacemos?", "Conseguido!", "Un respiro...", "Que sueno...", "Ey!", ""};

mochi_state_t mochi_state_from_name(const char *name)
{
    if (name && !strcmp(name, "question")) return MOCHI_CURIOUS;
    if (name && !strcmp(name, "error")) return MOCHI_OFFLINE;
    if (name) for (int i = 0; i < MOCHI_STATE_COUNT; i++) if (!strcmp(name, state_names[i])) return i;
    return MOCHI_IDLE;
}

void mochi_set_state(mochi_state_t next,int duration_ms)
{
    mochi_education_state(next);
    if (next<MOCHI_IDLE || next>=MOCHI_STATE_COUNT || !hint) return;
    state=next; sleeping=next==MOCHI_SLEEPING;
    int clip_ms=mochi_animation_duration(next);
    if (duration_ms>0 && clip_ms>duration_ms) duration_ms=clip_ms+100;
    state_until=duration_ms>0?esp_timer_get_time()+(int64_t)duration_ms*1000:0;
    mochi_animation_state(next);
    lv_label_set_text(hint,state_hints[next]);
    ESP_LOGI(TAG,"state: %s",state_names[next]);
}

void mochi_set_audio_level(float level)
{
    atomic_store(&audio_level_q10,(unsigned)(fminf(1,fmaxf(0,level))*1024));
}

void mochi_show_notice(const char *text,int duration_ms)
{
    mochi_education_notice(text,duration_ms);
    mochi_set_state(MOCHI_IDLE,duration_ms);
    lv_label_set_text(hint,text);
}

void mochi_set_voice_handlers(void (*start)(void),void (*stop)(void),bool (*busy)(void))
{
    voice_start=start; voice_stop=stop; voice_busy=busy;
}

void mochi_greet(void)
{
    mochi_set_state(MOCHI_HAPPY,2800);
    mochi_animation_play("greet");
    last_interaction=esp_timer_get_time();
}

void mochi_toggle_sleep(void)
{
    mochi_set_state(sleeping?MOCHI_IDLE:MOCHI_SLEEPING,0);
    last_interaction=esp_timer_get_time();
}

static void touch_event(lv_event_t *event)
{
    if (lv_event_get_code(event)==LV_EVENT_PRESSED) mochi_display_activity();
    if (mochi_interaction_blocked() || mochi_navigation_visible() || mochi_controls_power_pending()) return;
    lv_event_code_t code = lv_event_get_code(event);
    if (code == LV_EVENT_PRESSED) gesture_click = false;
    if (code == LV_EVENT_LONG_PRESSED && !gesture_click && voice_start && (!voice_busy || !voice_busy())) {
        touch_recording = true;
        voice_start();
    }
    if ((code == LV_EVENT_RELEASED || code == LV_EVENT_PRESS_LOST) && touch_recording) {
        touch_recording = false;
        if (voice_stop) voice_stop();
    }
    if (code == LV_EVENT_GESTURE && (!voice_busy || !voice_busy())) {
        lv_indev_t *gesture_input = lv_indev_active();
        lv_dir_t direction = gesture_input ? lv_indev_get_gesture_dir(gesture_input) : LV_DIR_NONE;
        if (direction == LV_DIR_LEFT || direction == LV_DIR_RIGHT) {
            gesture_click = true;
            mochi_set_state(MOCHI_IDLE,0);
            const char *id=mochi_animation_next(direction==LV_DIR_LEFT?1:-1);
            if (id) lv_label_set_text(hint,id);
        }
    }
    lv_indev_t *input = lv_indev_active();
    if (input && (code == LV_EVENT_PRESSED || code == LV_EVENT_PRESSING)) {
        lv_point_t point;
        lv_indev_get_point(input, &point);
        mochi_animation_look(fminf(1,fmaxf(-1,(point.x-233)/233.0f)),fminf(1,fmaxf(-1,(point.y-233)/233.0f)));
        last_interaction = esp_timer_get_time();
    }
    if (code == LV_EVENT_SHORT_CLICKED && !gesture_click && (!voice_busy || !voice_busy())) {
        int64_t now = esp_timer_get_time();
        if (sleeping) {
            mochi_greet();
            last_tap = 0;
        } else if (last_tap && now - last_tap < 350000) {
            mochi_toggle_sleep();
            last_tap = 0;
        } else {
            mochi_greet();
            last_tap = now;
        }
    }
}

static void animate(lv_timer_t *timer)
{
    if (hint) {
        if(mochi_education_active())lv_obj_add_flag(hint,LV_OBJ_FLAG_HIDDEN);
        else lv_obj_remove_flag(hint,LV_OBJ_FLAG_HIDDEN);
    }
    (void)timer;
    /* The actual output also repairs a missed UI state transition; speech
     * must never depend on acquiring the UI lock in the network worker. */
    mochi_output_status_t output; mochi_audio_output_status(&output);
    if (output.active && output.tap_ready && mochi_voice_busy() &&
        !mochi_interaction_blocked() && state!=MOCHI_SPEAKING) mochi_set_state(MOCHI_SPEAKING,0);
    bool visible=!settings_open && !mochi_navigation_visible() && (!mochi_dashboard_is_open() || mochi_dashboard_preview_active()) && !mochi_animation_uploading() && mochi_display_awake();
    bool charging_started=mochi_power_ui_tick(visible && !mochi_dashboard_is_open());
    if (charging_started && !mochi_voice_busy() && !mochi_voice_followup() &&
        state==MOCHI_IDLE && !mochi_interaction_blocked()) {
        mochi_appearance_t appearance;mochi_appearance_get(&appearance);
        mochi_set_state(MOCHI_HAPPY,2400);
        if (appearance.motion<2) mochi_animation_play("greet");
        lv_label_set_text(hint,"Cargando");
    }
    mochi_animation_tick(visible);
    if (!visible) return;
    int64_t now=esp_timer_get_time();
    if (state_until && now>state_until) mochi_set_state(MOCHI_IDLE,0);
    float seconds=now/1000000.0f;
    float level=atomic_load(&audio_level_q10)/1024.f;
    if (state==MOCHI_SPEAKING) level=mochi_audio_output_level()/1024.f;
    for (int i=0;i<3;i++) {
        bool active=state==MOCHI_THINKING || state==MOCHI_LISTENING || state==MOCHI_SPEAKING;
        if (active) lv_obj_remove_flag(dots[i],LV_OBJ_FLAG_HIDDEN);
        else lv_obj_add_flag(dots[i],LV_OBJ_FLAG_HIDDEN);
        int h=state==MOCHI_THINKING?6:5+(int)(level*(18+i*6));
        lv_obj_set_size(dots[i],6,h);
        lv_obj_set_pos(dots[i],212+i*18,375-h/2+(state==MOCHI_THINKING?(int)(sinf(seconds*5-i)*4):0));
    }
}

void mochi_create(lv_obj_t *screen)
{
    lv_obj_set_style_bg_color(screen,lv_color_black(),0);
    lv_obj_set_style_bg_opa(screen,LV_OPA_COVER,0);
    lv_obj_remove_flag(screen,LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_flag(screen,LV_OBJ_FLAG_CLICKABLE);
    lv_obj_add_event_cb(screen,touch_event,LV_EVENT_ALL,NULL);
    bool ready=mochi_animation_create(screen);
    mochi_power_ui_create(screen);
    hint=lv_label_create(screen);
    lv_label_set_text(hint,ready?"Toca o manten pulsado":"No se pudo cargar Mochi");
    lv_obj_set_style_text_font(hint,&mochi_font_14,0);
    lv_obj_set_style_text_color(hint,lv_color_hex(0xB4B7C4),0);
    lv_obj_set_width(hint,270);
    lv_obj_set_style_text_align(hint,LV_TEXT_ALIGN_CENTER,0);
    lv_obj_align(hint,LV_ALIGN_BOTTOM_MID,0,-52);
    lv_obj_remove_flag(hint,LV_OBJ_FLAG_CLICKABLE);
    for (int i=0;i<3;i++) {
        dots[i]=lv_obj_create(screen); lv_obj_remove_style_all(dots[i]);
        lv_obj_set_style_radius(dots[i],LV_RADIUS_CIRCLE,0);
        lv_obj_set_style_bg_color(dots[i],lv_color_hex(0xBFCBEA),0);
        lv_obj_set_style_bg_opa(dots[i],LV_OPA_COVER,0);
        lv_obj_remove_flag(dots[i],LV_OBJ_FLAG_CLICKABLE|LV_OBJ_FLAG_SCROLLABLE);
        lv_obj_add_flag(dots[i],LV_OBJ_FLAG_HIDDEN);
    }
    create_settings(screen); mochi_dashboard_create(screen); mochi_navigation_create(screen);
    mochi_education_create(screen);
    last_interaction=esp_timer_get_time();
    mochi_animation_bind_timer(lv_timer_create(animate,16,NULL));
    ESP_LOGI(TAG,"Mochi created: 466x466 Waveshare 1.75-G, original Coucou Canvas animations");
}
