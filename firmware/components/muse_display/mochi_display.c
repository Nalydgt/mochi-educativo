/* Adapted from Muse Gadget SDK board_waveshare_s3_175c.c.
 * Copyright (c) Meta Platforms, Inc. and affiliates.
 * SPDX-License-Identifier: Apache-2.0
 * See licenses/Muse-Apache-2.0.txt in the project root.
 *
 * Display and touch only; no Muse account, network or audio initialization.
 */
#include "mochi_display.h"
#include "mochi_lv_memory.h"
#include "bsp/esp-bsp.h"
#include "bsp/display.h"
#include "bsp/touch.h"
#include "esp_lcd_panel_io.h"
#include "esp_lv_adapter.h"
#include "esp_log.h"
#include "muse_lcd_bands.h"
#include "muse_mem.h"
#include "esp_timer.h"
#include <stdatomic.h>
#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "mochi_display";
static esp_lcd_panel_io_handle_t power_io;
static atomic_int_fast64_t activity_at;
static atomic_bool awake=true;
static atomic_int brightness=-1;
static atomic_uint rendered_frames;

typedef struct {
    int desired;
    esp_err_t result;
} brightness_change_t;

/* The LCD sender owns every SPI transaction, including brightness commands.
 * Sending parameters from the polling task can interrupt a band's window and
 * contend with its DMA transfers. No LVGL lock is needed for a panel command. */
static void set_brightness(void *argument)
{
    brightness_change_t *change=argument;
    int desired=change->desired;
    esp_err_t result=ESP_OK;
    if (desired) {
        if (!atomic_load(&awake))
            result=esp_lcd_panel_io_tx_param(power_io,(0x02<<24)|(0x29<<8),NULL,0);
        uint8_t value=desired;
        if (result==ESP_OK)
            result=esp_lcd_panel_io_tx_param(power_io,(0x02<<24)|(0x51<<8),&value,1);
    } else result=esp_lcd_panel_io_tx_param(power_io,(0x02<<24)|(0x28<<8),NULL,0);
    if (result==ESP_OK) {
        atomic_store(&awake,desired!=0);
        atomic_store(&brightness,desired);
    }
    change->result=result;
}

static void enable_te(void *argument)
{
    uint8_t vblank=0;
    esp_lcd_panel_io_tx_param(argument,(0x02<<24)|(0x35<<8),&vblank,1);
}

void mochi_display_activity(void) { atomic_store(&activity_at,esp_timer_get_time()); }
bool mochi_display_awake(void) { return atomic_load(&awake); }
void mochi_display_diagnose(void)
{
    bool locked=esp_lv_adapter_lock(50)==ESP_OK;
    if (locked) esp_lv_adapter_unlock();
    printf("@mochi_display_ui lock=%d awake=%d rendered=%u\n",locked,mochi_display_awake(),atomic_load(&rendered_frames));
    muse_lcd_bands_diagnose();
}

bool mochi_display_test(void)
{
    if (!power_io) return false;
    /* Exercise commands alongside live rendering without changing preferences. */
    bool passed=true;
    for (unsigned i=0;i<12;i++) {
        brightness_change_t change={.desired=(i%2)?190:35};
        muse_lcd_bands_run(set_brightness,&change);
        passed &= change.result==ESP_OK;
        vTaskDelay(pdMS_TO_TICKS(80));
    }
    mochi_display_activity();
    mochi_display_diagnose();
    return passed;
}
void mochi_display_poll(bool portable,bool force_awake)
{
    if (!power_io) return;
    if (force_awake) mochi_display_activity();
    int64_t idle=esp_timer_get_time()-atomic_load(&activity_at);
    int desired=!portable || idle<20000000 ? 190 : idle<60000000 ? 35 : 0;
    if (desired==atomic_load(&brightness)) return;
    brightness_change_t change={.desired=desired};
    muse_lcd_bands_run(set_brightness,&change);
    if (change.result!=ESP_OK)
        ESP_LOGW(TAG,"Brightness update failed: %s",esp_err_to_name(change.result));
}

static void round_area(lv_event_t *event)
{
    lv_area_t *area = lv_event_get_param(event);
    area->x1 &= ~1;
    area->y1 &= ~1;
    area->x2 |= 1;
    area->y2 |= 1;
}
static void touch_activity(lv_event_t *event) { (void)event; mochi_display_activity(); }
static void frame_rendered(lv_event_t *event) { (void)event;atomic_fetch_add(&rendered_frames,1); }

lv_display_t *mochi_display_start(void)
{
    if(!mochi_lv_memory_ready()){
        ESP_LOGE(TAG,"PSRAM unavailable for the display heap");return NULL;
    }
    if (bsp_i2c_init() != ESP_OK) return NULL;
    esp_lv_adapter_config_t config = ESP_LV_ADAPTER_DEFAULT_CONFIG();
    config.task_core_id = MUSE_UI_CORE;
    config.task_priority = MUSE_UI_PRIORITY;
    if (esp_lv_adapter_init(&config) != ESP_OK) return NULL;

    esp_lcd_panel_handle_t panel;
    esp_lcd_panel_io_handle_t io;
    /* One 16-row DMA buffer uses the same internal memory as the former two
     * 8-row buffers, with half as many command/interrupt round trips. */
    const size_t chunk_bytes = BSP_LCD_H_RES * 16 * 2;
    bsp_display_config_t panel_config = {.max_transfer_sz = chunk_bytes};
    if (bsp_display_new(&panel_config, &panel, &io) != ESP_OK) return NULL;
    power_io=io; mochi_display_activity();
    const esp_lv_adapter_display_config_t display_config = {
        .panel = panel,
        .panel_io = io,
        .profile = {
            .interface = ESP_LV_ADAPTER_PANEL_IF_OTHER,
            .rotation = ESP_LV_ADAPTER_ROTATE_0,
            .hor_res = BSP_LCD_H_RES,
            .ver_res = BSP_LCD_V_RES,
        },
        .tear_avoid_mode = ESP_LV_ADAPTER_TEAR_AVOID_MODE_NONE,
    };
    /* A complete LVGL dirty region fits in one PSRAM buffer. Moving limbs
     * must not be presented as independently timed 118-row bands. */
    lv_display_t *display = muse_lcd_bands_register(display_config, BSP_LCD_V_RES, chunk_bytes);
    if (!display) return NULL;
    lv_display_add_event_cb(display, round_area, LV_EVENT_INVALIDATE_AREA, NULL);
    lv_display_add_event_cb(display, frame_rendered, LV_EVENT_RENDER_READY, NULL);
    muse_lcd_bands_run(enable_te,io);
    muse_lcd_bands_set_te(13);

    bsp_display_cfg_t touch_config = {.touch_flags = {.mirror_x = 1, .mirror_y = 1}};
    esp_lcd_touch_handle_t touch;
    if (bsp_touch_new(&touch_config, &touch) != ESP_OK) return NULL;
    const esp_lv_adapter_touch_config_t input_config = ESP_LV_ADAPTER_TOUCH_DEFAULT_CONFIG(display, touch);
    lv_indev_t *input=esp_lv_adapter_register_touch(&input_config);
    if (!input) return NULL;
    lv_indev_add_event_cb(input,touch_activity,LV_EVENT_PRESSED,NULL);
    if (esp_lv_adapter_start() != ESP_OK) return NULL;
    ESP_LOGI(TAG, "Muse display transport ready, 466x466, CST9217 touch");
    return display;
}
