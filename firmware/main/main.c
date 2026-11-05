#include "driver/gpio.h"
#include "esp_log.h"
#include "esp_system.h"
#include "esp_lv_adapter.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "mochi.h"
#include "mochi_display.h"
#include "mochi_runtime.h"
#include "mochi_controls.h"
#include "mochi_gps.h"
#include "mochi_audio.h"
#include "mochi_options.h"
#include "mochi_appearance.h"
#include "mochi_motion_sensor.h"
#include "mochi_resources.h"
#include "mochi_voice_policy.h"
#include "esp_ota_ops.h"
#include "esp_app_desc.h"
#include "mochi_fonts.h"

static const char *TAG = "mochi";

void app_main(void)
{
    ESP_LOGI(TAG, "Mochi %s | Coucou native | Waveshare 1.75-G | ESP-IDF 6.0.1", esp_app_get_description()->version);
    lv_display_t *display = mochi_display_start();
    if (!display) {
        ESP_LOGE(TAG, "Display initialization failed");
        return;
    }
    mochi_controls_init();
    mochi_options_init(); mochi_appearance_init(); mochi_motion_sensor_init();
    /* Reserve internal DMA memory before Wi-Fi/Tailscale tasks fragment it.
     * Output stays muted; no samples are read, sent, or played here. */
    if (mochi_audio_init() != ESP_OK) ESP_LOGE(TAG, "Audio unavailable; continuing without voice");
    if (!mochi_runtime_reserve_audio()) ESP_LOGE(TAG,"Audio reply memory unavailable");
    mochi_gps_start();
    if (esp_lv_adapter_lock(3000) != ESP_OK) {
        ESP_LOGE(TAG, "Display lock timed out");
        return;
    }
    mochi_fonts_init();
    lv_obj_set_style_text_font(lv_screen_active(),&mochi_font_16,0);
    mochi_create(lv_screen_active());
    esp_lv_adapter_unlock();
    mochi_runtime_start();
    mochi_resources_start();
    if (esp_lv_adapter_lock(1000) == ESP_OK) {
        mochi_set_voice_handlers(mochi_voice_start, mochi_voice_stop, mochi_voice_busy);
        esp_lv_adapter_unlock();
    }

    gpio_config_t button = {
        .pin_bit_mask = 1ULL << GPIO_NUM_0,
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&button));
    ESP_LOGI(TAG, "READY: animated avatar, touch to greet, BOOT to sleep/wake");

    bool was_down = false;
    int64_t last_change = 0;
    int64_t pressed_at = 0;
    bool button_recording = false;
    bool button_consumed = false;
    unsigned heartbeat = 0;
    bool startup_checked=false;
    while (true) {
        mochi_controls_poll();
        mochi_motion_sensor_poll();
        if (mochi_motion_sensor_lifted() && !mochi_interaction_blocked() && !mochi_voice_busy() && !mochi_voice_followup()) {
            mochi_options_t options; mochi_options_get(&options);
            if (options.power_mode==MOCHI_POWER_HOME && esp_lv_adapter_lock(50)==ESP_OK) { mochi_greet(); esp_lv_adapter_unlock(); }
        }
        if (!startup_checked && esp_timer_get_time()>=30000000) {
            startup_checked=true;
            const esp_partition_t *running=esp_ota_get_running_partition(); esp_ota_img_states_t state;
            if (running && esp_ota_get_state_partition(running,&state)==ESP_OK && state==ESP_OTA_IMG_PENDING_VERIFY) {
                mochi_output_status_t output; mochi_audio_output_status(&output);
                bool healthy=output.tap_ready && output.sequence>0 && mochi_runtime_reserve_audio() &&
                    mochi_voice_policy_self_test() && mochi_audio_self_test();
                esp_err_t result=healthy?esp_ota_mark_app_valid_cancel_rollback():ESP_FAIL;
                ESP_LOGI(TAG,"OTA startup validation: healthy=%d result=%s",healthy,esp_err_to_name(result));
            }
        }
        bool down = gpio_get_level(GPIO_NUM_0) == 0;
        int64_t now = esp_timer_get_time();
        if (down != was_down && now - last_change > 60000) {
            was_down = down;
            last_change = now;
            if (down) {
                pressed_at = now; mochi_display_activity();
                button_consumed=mochi_voice_busy() || mochi_voice_followup();
                if (button_consumed) mochi_voice_cancel();
            }
            else if (button_consumed) { button_consumed=false; }
            else if (button_recording) {
                mochi_voice_stop();
                button_recording = false;
            } else if (now - pressed_at < 350000 && !mochi_voice_busy() && esp_lv_adapter_lock(100) == ESP_OK) {
                mochi_toggle_sleep();
                esp_lv_adapter_unlock();
            }
        }
        if (down && !button_recording && !button_consumed && now - pressed_at >= 350000) {
            button_recording = true;
            mochi_voice_start();
        }
        if (++heartbeat % 1000 == 0) {
            ESP_LOGI(TAG, "alive: uptime=%llds free_heap=%lu", now / 1000000,
                     (unsigned long)esp_get_free_heap_size());
        }
        vTaskDelay(pdMS_TO_TICKS(20));
    }
}
