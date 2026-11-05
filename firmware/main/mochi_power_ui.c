#include "mochi_power_ui.h"
#include "mochi_controls.h"
#include "mochi_appearance.h"
#include "mochi_fonts.h"
#include "esp_timer.h"
#include <stdio.h>
#include <string.h>

static lv_obj_t *indicator,*shell,*fill,*shine,*cap,*bolt,*percent;
static int64_t updated;
static bool charging_seen,visible_seen;
static mochi_power_status_t displayed={.percent=-1};

static lv_obj_t *shape(lv_obj_t *parent,int x,int y,int width,int height,uint32_t colour)
{
    lv_obj_t *object=lv_obj_create(parent);
    lv_obj_remove_style_all(object);
    lv_obj_set_pos(object,x,y);lv_obj_set_size(object,width,height);
    lv_obj_set_style_radius(object,2,0);
    lv_obj_set_style_bg_color(object,lv_color_hex(colour),0);
    lv_obj_set_style_bg_opa(object,LV_OPA_COVER,0);
    lv_obj_remove_flag(object,LV_OBJ_FLAG_CLICKABLE|LV_OBJ_FLAG_SCROLLABLE);
    return object;
}

void mochi_power_ui_create(lv_obj_t *screen)
{
    /* Entire 98 x 26 indicator stays inside the circular panel's top safe area. */
    indicator=shape(screen,184,43,98,26,0);
    lv_obj_set_style_bg_opa(indicator,LV_OPA_TRANSP,0);
    shell=shape(indicator,0,4,34,18,0);
    lv_obj_set_style_bg_opa(shell,LV_OPA_TRANSP,0);
    lv_obj_set_style_border_width(shell,2,0);
    lv_obj_set_style_border_color(shell,lv_color_hex(0xB4B7C4),0);
    cap=shape(indicator,35,9,3,8,0xB4B7C4);
    fill=shape(indicator,4,8,0,10,0xB4B7C4);
    lv_obj_set_style_clip_corner(fill,true,0);
    shine=shape(fill,-5,0,5,10,0xD9FFE9);
    bolt=lv_label_create(indicator);
    lv_label_set_text(bolt,LV_SYMBOL_CHARGE);
    lv_obj_set_style_text_font(bolt,&mochi_font_14,0);
    lv_obj_set_style_text_color(bolt,lv_color_hex(0x9AE8BE),0);
    lv_obj_set_pos(bolt,41,4);
    lv_obj_remove_flag(bolt,LV_OBJ_FLAG_CLICKABLE);
    percent=lv_label_create(indicator);
    lv_label_set_text(percent,"--");
    lv_obj_set_style_text_font(percent,&mochi_font_14,0);
    lv_obj_set_style_text_color(percent,lv_color_hex(0xDADCE5),0);
    lv_obj_set_pos(percent,55,4);lv_obj_set_width(percent,43);
    lv_obj_remove_flag(percent,LV_OBJ_FLAG_CLICKABLE);
    lv_obj_add_flag(bolt,LV_OBJ_FLAG_HIDDEN);
    lv_obj_add_flag(shine,LV_OBJ_FLAG_HIDDEN);
    lv_obj_add_flag(fill,LV_OBJ_FLAG_HIDDEN);
    lv_obj_add_flag(indicator,LV_OBJ_FLAG_HIDDEN);
}

bool mochi_power_ui_tick(bool visible)
{
    if (!indicator) return false;
    if (visible!=visible_seen) {
        if (visible) lv_obj_remove_flag(indicator,LV_OBJ_FLAG_HIDDEN);
        else lv_obj_add_flag(indicator,LV_OBJ_FLAG_HIDDEN);
        visible_seen=visible;
    }
    int64_t now=esp_timer_get_time();
    if (now-updated<100000) return false;
    updated=now;
    mochi_power_status_t power;mochi_controls_power_status(&power);
    bool charging=power.valid && power.usb && power.charging;
    bool started=charging && !charging_seen;
    /* An unreadable PMU sample must not manufacture another plug-in event. */
    if (power.valid) charging_seen=charging;
    int value=power.valid && power.percent>=0 && power.percent<=100?power.percent:-1;
    uint32_t colour=charging?0x9AE8BE:value>=0 && value<=15?0xFF939E:0xB4B7C4;
    char text[12];
    if (value>=0) snprintf(text,sizeof(text),"%d%%",value);
    else snprintf(text,sizeof(text),"--");
    if (strcmp(lv_label_get_text(percent),text)) lv_label_set_text(percent,text);
    lv_obj_set_style_border_color(shell,lv_color_hex(colour),0);
    lv_obj_set_style_bg_color(cap,lv_color_hex(colour),0);
    lv_obj_set_style_bg_color(fill,lv_color_hex(colour),0);
    int width=value>0?(26*value+99)/100:0;
    lv_obj_set_width(fill,width);
    if (width) lv_obj_remove_flag(fill,LV_OBJ_FLAG_HIDDEN);
    else lv_obj_add_flag(fill,LV_OBJ_FLAG_HIDDEN);
    if (charging) lv_obj_remove_flag(bolt,LV_OBJ_FLAG_HIDDEN);
    else lv_obj_add_flag(bolt,LV_OBJ_FLAG_HIDDEN);
    mochi_appearance_t appearance;mochi_appearance_get(&appearance);
    bool animate=visible && charging && width && appearance.motion<2;
    if (animate) {
        lv_obj_set_style_bg_opa(fill,LV_OPA_60,0);
        lv_obj_remove_flag(shine,LV_OBJ_FLAG_HIDDEN);
        lv_obj_set_x(shine,-5+(int)((now%1600000)*(width+5)/1600000));
    } else {
        lv_obj_set_style_bg_opa(fill,LV_OPA_COVER,0);
        lv_obj_add_flag(shine,LV_OBJ_FLAG_HIDDEN);
    }
    displayed=power;
    return started && visible;
}

void mochi_power_ui_diagnose(void)
{
    printf("@mochi_power_ui visible=%d valid=%d usb=%d charging=%d percent=%d animated=%d x=184 y=43 width=98 height=26\n",
        indicator && lv_obj_is_visible(indicator),displayed.valid,displayed.usb,
        displayed.valid && displayed.usb && displayed.charging,
        displayed.percent,shine && lv_obj_is_visible(shine));
    fflush(stdout);
}
