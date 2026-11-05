/* AXP2101 register access follows Muse Gadget SDK muse_pmu.c.
 * Copyright (c) Meta Platforms, Inc. and affiliates. Apache-2.0.
 * Only the power-key timer and explicit shutdown command are changed here. */
#include "mochi_controls.h"
#include "mochi_audio.h"
#include "mochi_runtime.h"
#include "mochi.h"
#include "mochi_options.h"
#include "mochi_appearance.h"
#include "mochi_display.h"
#include "esp_sleep.h"
#include "esp_wifi.h"
#include "bsp/esp-bsp.h"
#include "driver/i2c_master.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_lv_adapter.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "nvs.h"
#include "nvs_flash.h"
#include <stdatomic.h>
#include <stdio.h>

static i2c_master_dev_handle_t pmu;
static bool pmu_ready, storage_ready, off_attempted;
static atomic_bool off_requested;
static atomic_int persisted_volume = -1;
static int observed_volume = 45;
static int64_t volume_changed, off_at;
static atomic_bool deep_requested;
static mochi_power_status_t power_status={.percent=-1};
static portMUX_TYPE power_lock=portMUX_INITIALIZER_UNLOCKED;
static int64_t power_polled;

void mochi_controls_power_status(mochi_power_status_t *out)
{
    portENTER_CRITICAL(&power_lock); *out=power_status; portEXIT_CRITICAL(&power_lock);
}
void mochi_controls_request_deep(void) { mochi_voice_cancel(); atomic_store(&deep_requested,true); }

static esp_err_t read_reg(uint8_t reg, uint8_t *value)
{
    return i2c_master_transmit_receive(pmu, &reg, 1, value, 1, 50);
}

static esp_err_t write_reg(uint8_t reg, uint8_t value)
{
    const uint8_t bytes[] = {reg, value};
    return i2c_master_transmit(pmu, bytes, sizeof(bytes), 50);
}

static void save_volume(void)
{
    int value = mochi_audio_get_volume();
    if (!storage_ready || value == persisted_volume) return;
    nvs_handle_t handle;
    if (nvs_open("mochi_ui", NVS_READWRITE, &handle) != ESP_OK) return;
    esp_err_t error = nvs_set_u8(handle, "volume", value);
    if (error == ESP_OK) error = nvs_commit(handle);
    nvs_close(handle);
    if (error == ESP_OK) persisted_volume = value;
    else ESP_LOGW("mochi_controls", "Volume save failed: %s", esp_err_to_name(error));
}

void mochi_controls_init(void)
{
    storage_ready = nvs_flash_init() == ESP_OK;
    nvs_handle_t handle;
    uint8_t value = 45;
    if (storage_ready && nvs_open("mochi_ui", NVS_READONLY, &handle) == ESP_OK) {
        if (nvs_get_u8(handle, "volume", &value) == ESP_OK && value <= 100) persisted_volume = value;
        else value = 45;
        nvs_close(handle);
    }
    mochi_audio_set_volume(value);
    observed_volume = value;
    i2c_device_config_t device = {.dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = 0x34, .scl_speed_hz = 400000};
    uint8_t timer, off_control;
    if (i2c_master_bus_add_device(bsp_i2c_get_handle(), &device, &pmu) == ESP_OK &&
        read_reg(0x27, &timer) == ESP_OK &&
        write_reg(0x27, (timer & ~0x0c) | 0x0c) == ESP_OK &&
        read_reg(0x22, &off_control) == ESP_OK &&
        /* XPowersLib: enableLongPressShutdown + setLongPressPowerOFF. */
        write_reg(0x22, (off_control | 2) & ~1) == ESP_OK) pmu_ready = true;
    ESP_LOGI("mochi_controls", "Volume %d; PMU %s; PWR hold-off 10 s", value, pmu_ready ? "ready" : "unavailable");
}

bool mochi_controls_power_pending(void) { return atomic_load(&off_requested); }

bool mochi_controls_request_off(void)
{
    if (!pmu_ready || mochi_voice_busy()) return false;
    atomic_store(&off_requested, true);
    return true;
}

void mochi_controls_poll(void)
{
    int64_t now = esp_timer_get_time();
    mochi_options_poll();
    mochi_appearance_poll();
    mochi_options_t options; mochi_options_get(&options);
    mochi_display_poll(options.power_mode==MOCHI_POWER_WALK,mochi_voice_busy() || mochi_voice_followup());
    if (pmu_ready && now-power_polled>=2000000) {
        power_polled=now; uint8_t status1=0,status2=0,pct=255,hi=0,lo=0;
        mochi_power_status_t snapshot={.percent=-1};
        if (read_reg(0x00,&status1)==ESP_OK && read_reg(0x01,&status2)==ESP_OK) {
            snapshot.valid=true; snapshot.usb=!!(status1&0x20);
            bool battery=!!(status1&8); snapshot.charging=battery && ((status2>>5)&3)==1;
            if (battery && read_reg(0xa4,&pct)==ESP_OK && pct<=100) snapshot.percent=pct;
            if (battery && read_reg(0x34,&hi)==ESP_OK && read_reg(0x35,&lo)==ESP_OK) snapshot.millivolts=((hi&0x1f)<<8)|lo;
        }
        portENTER_CRITICAL(&power_lock);
        bool plugged=snapshot.valid && snapshot.usb && power_status.valid && !power_status.usb;
        power_status=snapshot;
        portEXIT_CRITICAL(&power_lock);
        if (plugged) mochi_display_activity();
    }
    if (atomic_load(&deep_requested) && !mochi_voice_busy()) {
        save_volume(); mochi_options_flush(); mochi_appearance_flush();
        /* BOOT is RTC GPIO0. Do not sleep while it is already held low. */
        if (gpio_get_level(GPIO_NUM_0)) {
            esp_sleep_enable_ext0_wakeup(GPIO_NUM_0,0);
            esp_wifi_stop(); esp_deep_sleep_start();
        }
    }
    int value = mochi_audio_get_volume();
    if (value != observed_volume) {
        observed_volume = value;
        volume_changed = now;
    }
    if (value != persisted_volume && now - volume_changed >= 700000) {
        save_volume();
        volume_changed = now;
    }
    if (!mochi_controls_power_pending() || off_attempted || mochi_voice_busy()) return;
    if (!off_at) { off_at = now + 600000; return; }
    if (now < off_at) return;
    save_volume();
    mochi_options_flush(); mochi_appearance_flush();
    off_attempted = true;
    uint8_t common;
    esp_err_t error = read_reg(0x10, &common);
    if (error == ESP_OK) error = write_reg(0x10, common | 1);
    ESP_LOGI("mochi_controls", "PMU shutdown command: %s", esp_err_to_name(error));
    /* If USB keeps the board powered, keep the screen honest and usable. */
    vTaskDelay(pdMS_TO_TICKS(1200));
    atomic_store(&off_requested, false);
    off_attempted = false;
    off_at = 0;
    if (esp_lv_adapter_lock(200) == ESP_OK) {
        mochi_show_notice(error == ESP_OK ? "Desconecta el USB para apagar" : "Usa PWR 10 s para apagar", 8000);
        esp_lv_adapter_unlock();
    }
}

void mochi_controls_diagnose(void)
{
    uint8_t timer = 0, status = 0, off_control = 0;
    bool ok = pmu_ready && read_reg(0x27, &timer) == ESP_OK && read_reg(0x00, &status) == ESP_OK &&
        read_reg(0x22, &off_control) == ESP_OK;
    printf("@mochi_controls volume=%d saved=%d pmu=%d hold10=%d usb=%d pending=%d\n",
        mochi_audio_get_volume(), atomic_load(&persisted_volume), ok,
        ok && (timer & 0x0c) == 0x0c && (off_control & 3) == 2,
        ok && !!(status & 0x20), mochi_controls_power_pending());
    fflush(stdout);
}
