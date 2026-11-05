/* The stereo codec setup and high-pass filter follow Muse Gadget SDK
 * muse_audio.c. Copyright (c) Meta Platforms, Inc. and affiliates.
 * SPDX-License-Identifier: Apache-2.0 */
#include "mochi_audio.h"
#include "bsp/esp-bsp.h"
#include "esp_codec_dev.h"
#include "esp_log.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "esp_attr.h"
#include "driver/i2s_std.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <math.h>
#include <stdatomic.h>
#include <stdio.h>

static esp_codec_dev_handle_t speaker, microphone;
static int16_t stereo[MOCHI_AUDIO_FRAMES * 2];
static float previous_x, previous_y;
static bool ready, attempted, playback_pending;
static atomic_int volume = 45;
static int applied_volume = -1;
static int64_t playback_started;
static size_t playback_frames;
static atomic_uint last_pcm_ms,last_wall_ms;
static DRAM_ATTR atomic_bool output_active;
static DRAM_ATTR atomic_uint output_level,output_mean,output_tick,output_sequence;
static DRAM_ATTR atomic_bool output_first_seen;
static DRAM_ATTR atomic_uint output_first_tick;
static bool output_tap_ready;
extern i2s_chan_handle_t mochi_board_audio_tx_channel(void);

/* Runs after a DMA buffer has actually reached the DAC and before the BSP's
 * auto-clear. Only bounded integer work, internal atomics, no LVGL or audio IO. */
static bool IRAM_ATTR output_sent(i2s_chan_handle_t channel,i2s_event_data_t *event,void *context)
{
    (void)channel; (void)context;
    unsigned mean=0,peak=0,sum=0;
    if (atomic_load_explicit(&output_active,memory_order_relaxed) && event->dma_buf) {
        const int16_t *pcm=event->dma_buf;
        for (size_t i=0;i<event->size/sizeof(int16_t);i+=2) {
            int value=pcm[i]; unsigned magnitude=value<0?(unsigned)-value:(unsigned)value;
            sum+=magnitude; if (magnitude>peak) peak=magnitude;
        }
        /* BSP uses 240 stereo frames per DMA descriptor. */
        mean=event->size==960?sum/240:peak;
    }
    unsigned tick=(unsigned)xTaskGetTickCountFromISR();
    /* Timestamp completed nonzero PCM, not the first write queued ahead of
     * the amplifier's silence lead. This measures DAC output, not room sound. */
    if (peak && !atomic_load_explicit(&output_first_seen,memory_order_relaxed)) {
        atomic_store_explicit(&output_first_tick,tick,memory_order_relaxed);
        atomic_store_explicit(&output_first_seen,true,memory_order_release);
    }
    unsigned level=mean<90?0:(mean*1024)/5000;
    if (atomic_load_explicit(&volume,memory_order_relaxed)==0) level=0;
    if (level>1024) level=1024;
    atomic_store_explicit(&output_mean,mean,memory_order_relaxed);
    atomic_store_explicit(&output_level,level,memory_order_relaxed);
    atomic_store_explicit(&output_tick,tick,memory_order_release);
    atomic_fetch_add_explicit(&output_sequence,1,memory_order_relaxed);
    return false;
}

void mochi_audio_output_status(mochi_output_status_t *out)
{
    unsigned last=atomic_load_explicit(&output_tick,memory_order_acquire);
    out->age_ms=pdTICKS_TO_MS((TickType_t)((unsigned)xTaskGetTickCount()-last));
    out->active=atomic_load(&output_active); out->tap_ready=output_tap_ready;
    out->mean_abs=atomic_load(&output_mean); out->sequence=atomic_load(&output_sequence);
    out->first_nonzero_seen=atomic_load_explicit(&output_first_seen,memory_order_acquire);
    out->first_nonzero_tick=atomic_load_explicit(&output_first_tick,memory_order_relaxed);
    out->level_q10=out->active && out->age_ms<=80?atomic_load(&output_level):0;
}

unsigned mochi_audio_output_level(void)
{
    mochi_output_status_t status; mochi_audio_output_status(&status); return status.level_q10;
}

static esp_err_t attach_output_tap(void)
{
    i2s_chan_handle_t channel=mochi_board_audio_tx_channel();
    i2s_chan_info_t info;
    if (!channel || i2s_channel_get_info(channel,&info)!=ESP_OK) return ESP_ERR_INVALID_STATE;
    esp_err_t result=info.is_enabled?i2s_channel_disable(channel):ESP_OK;
    if (result!=ESP_OK) return result;
    const i2s_event_callbacks_t callbacks={.on_sent=output_sent};
    result=i2s_channel_register_event_callback(channel,&callbacks,NULL);
    esp_err_t enabled=info.is_enabled?i2s_channel_enable(channel):ESP_OK;
    if (result==ESP_OK) result=enabled;
    output_tap_ready=result==ESP_OK;
    return result;
}

int mochi_audio_get_volume(void) { return atomic_load(&volume); }
void mochi_audio_set_volume(int percent)
{
    atomic_store(&volume, percent < 0 ? 0 : percent > 100 ? 100 : percent);
}

/* Only the audio worker touches codec registers, including during playback. */
static esp_err_t apply_volume(void)
{
    int desired = mochi_audio_get_volume();
    if (desired == applied_volume) return ESP_OK;
    if (esp_codec_dev_set_out_vol(speaker, desired) != ESP_CODEC_DEV_OK ||
        esp_codec_dev_set_out_mute(speaker, desired == 0) != ESP_CODEC_DEV_OK) return ESP_FAIL;
    applied_volume = desired;
    return ESP_OK;
}

esp_err_t mochi_audio_init(void)
{
    if (ready) return ESP_OK;
    /* BSP owns the I2S handles and cannot safely retry a partial init. */
    if (attempted) return ESP_ERR_INVALID_STATE;
    attempted = true;
    if (heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_DMA) < 24576) {
        ESP_LOGE("mochi_audio", "Insufficient internal memory for audio DMA");
        return ESP_ERR_NO_MEM;
    }
    speaker = bsp_audio_codec_speaker_init();
    microphone = bsp_audio_codec_microphone_init();
    if (!speaker || !microphone) return ESP_FAIL;
    esp_err_t tap_error=attach_output_tap();
    if (tap_error!=ESP_OK) return tap_error;
    /* open() reapplies these settings. Keep the amplifier muted until playback. */
    esp_codec_dev_set_out_vol(speaker, 0);
    esp_codec_dev_set_out_mute(speaker, true);
    esp_codec_dev_sample_info_t format = {.sample_rate = MOCHI_SAMPLE_RATE, .channel = 2, .bits_per_sample = 16};
    if (esp_codec_dev_open(speaker, &format) != ESP_CODEC_DEV_OK) return ESP_FAIL;
    if (esp_codec_dev_open(microphone, &format) != ESP_CODEC_DEV_OK) {
        esp_codec_dev_close(speaker);
        return ESP_FAIL;
    }
    applied_volume = -1;
    if (esp_codec_dev_set_out_mute(speaker, true) != ESP_CODEC_DEV_OK ||
        esp_codec_dev_set_in_gain(microphone, 30) != ESP_CODEC_DEV_OK) {
        esp_codec_dev_close(speaker);
        esp_codec_dev_close(microphone);
        return ESP_FAIL;
    }
    ready = true;
    ESP_LOGI("mochi_audio", "Codecs ready: 16000 Hz, stereo bus, mono conversation");
    return ESP_OK;
}

void mochi_audio_idle(void)
{
    if (ready) {
        /* Six 240-frame DMA buffers can still contain the end of the reply. */
        if (playback_pending) {
            vTaskDelay(pdMS_TO_TICKS(120));
            atomic_store(&last_pcm_ms,(unsigned)(playback_frames*1000/MOCHI_SAMPLE_RATE));
            atomic_store(&last_wall_ms,(unsigned)((esp_timer_get_time()-playback_started)/1000));
        }
        esp_codec_dev_set_out_mute(speaker, true);
        atomic_store(&output_active,false); atomic_store(&output_level,0);
        playback_pending = false;
        applied_volume = -1;
    }
}

void mochi_audio_diagnose(void)
{
    printf("@mochi_audio ready=%d attempted=%d volume=%d internal_free=%u dma_largest=%u console_stack_free=%u psram_free=%u psram_largest=%u\n",
           ready, attempted, mochi_audio_get_volume(),
           (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT),
           (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL | MALLOC_CAP_DMA),
           (unsigned)uxTaskGetStackHighWaterMark(NULL),
           (unsigned)heap_caps_get_free_size(MALLOC_CAP_SPIRAM),
           (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM));
    fflush(stdout);
    printf("@mochi_playback pcm_ms=%u wall_ms=%u lead_ms=128\n",atomic_load(&last_pcm_ms),atomic_load(&last_wall_ms));
    mochi_output_status_t output; mochi_audio_output_status(&output);
    printf("@mochi_output tap=%d active=%d level=%u mean=%u age_ms=%u sequence=%u\n",
        output.tap_ready,output.active,output.level_q10,output.mean_abs,output.age_ms,output.sequence);
    static const char *names[] = {"ml_derp_tx", "ml_derp_rx", "ml_coord", "ml_wg_mgr", "mochi_voice", "mochi_nav"};
    for (size_t i = 0; i < sizeof(names) / sizeof(names[0]); i++) {
        TaskHandle_t task = xTaskGetHandle(names[i]);
        if (task) printf("@mochi_stack task=%s free=%u\n", names[i], (unsigned)uxTaskGetStackHighWaterMark(task));
    }
    fflush(stdout);
}

/* Exercise the real codec open() error path without touching hardware. */
typedef struct {
    audio_codec_data_if_t interface;
    int format_result, enable_result, enable_calls;
} codec_probe_t;

static int probe_format(const audio_codec_data_if_t *h, esp_codec_dev_type_t type,
                        esp_codec_dev_sample_info_t *format)
{
    (void)type; (void)format;
    return ((codec_probe_t *)h)->format_result;
}

static int probe_enable(const audio_codec_data_if_t *h, esp_codec_dev_type_t type, bool enable)
{
    (void)type;
    codec_probe_t *probe = (codec_probe_t *)h;
    if (enable) probe->enable_calls++;
    return probe->enable_result;
}

static int probe_read(const audio_codec_data_if_t *h, uint8_t *data, int size)
{
    (void)h; (void)data; (void)size;
    return ESP_CODEC_DEV_OK;
}

bool mochi_audio_self_test(void)
{
    codec_probe_t probe = {.interface = {.set_fmt = probe_format, .enable = probe_enable, .read = probe_read},
                           .format_result = ESP_CODEC_DEV_NO_MEM};
    esp_codec_dev_cfg_t cfg = {.dev_type = ESP_CODEC_DEV_TYPE_IN, .data_if = &probe.interface};
    esp_codec_dev_handle_t dev = esp_codec_dev_new(&cfg);
    if (!dev) return false;
    esp_codec_dev_sample_info_t format = {.sample_rate = MOCHI_SAMPLE_RATE, .channel = 2, .bits_per_sample = 16};
    uint8_t sample[4];
    bool pass = esp_codec_dev_open(dev, &format) == ESP_CODEC_DEV_NO_MEM && probe.enable_calls == 0;
    pass &= esp_codec_dev_read(dev, sample, sizeof(sample)) == ESP_CODEC_DEV_WRONG_STATE;
    probe.format_result = ESP_CODEC_DEV_OK;
    probe.enable_result = ESP_CODEC_DEV_DRV_ERR;
    pass &= esp_codec_dev_open(dev, &format) == ESP_CODEC_DEV_DRV_ERR && probe.enable_calls == 1;
    pass &= esp_codec_dev_read(dev, sample, sizeof(sample)) == ESP_CODEC_DEV_WRONG_STATE;
    probe.enable_result = ESP_CODEC_DEV_OK;
    pass &= esp_codec_dev_open(dev, &format) == ESP_CODEC_DEV_OK && probe.enable_calls == 2;
    esp_codec_dev_delete(dev);
    return pass;
}

esp_err_t mochi_audio_read(int16_t *mono, size_t frames)
{
    if (!ready || frames > MOCHI_AUDIO_FRAMES) return ESP_ERR_INVALID_STATE;
    if (esp_codec_dev_read(microphone, stereo, frames * 4) != ESP_CODEC_DEV_OK) return ESP_FAIL;
    const float alpha = 0.96954f; /* 80 Hz high-pass at 16 kHz */
    for (size_t i = 0; i < frames; i++) {
        float x = 0.5f * (stereo[2 * i] + stereo[2 * i + 1]);
        float y = alpha * (previous_y + x - previous_x);
        previous_x = x;
        previous_y = y;
        mono[i] = (int16_t)fminf(32767, fmaxf(-32768, y));
    }
    return ESP_OK;
}

esp_err_t mochi_audio_write(const int16_t *mono, size_t frames)
{
    if (!ready || frames > MOCHI_AUDIO_FRAMES) return ESP_ERR_INVALID_STATE;
    if (apply_volume() != ESP_OK) return ESP_FAIL;
    if (!playback_pending) {
        playback_started=esp_timer_get_time(); playback_frames=0;
        atomic_store(&output_first_seen,false);
        atomic_store(&output_level,0); atomic_store(&output_active,true);
        /* Unmute onto silence while the DAC/amplifier settles. These eight
         * blocks precede the first phoneme; none of the voice is discarded. */
        for (size_t i=0;i<MOCHI_AUDIO_FRAMES*2;i++) stereo[i]=0;
        for (int i=0;i<8;i++) {
            if (esp_codec_dev_write(speaker,stereo,sizeof(stereo))!=ESP_CODEC_DEV_OK) return ESP_FAIL;
            playback_pending=true;
        }
    }
    for (size_t i = 0; i < frames; i++) stereo[2 * i] = stereo[2 * i + 1] = mono[i];
    if (esp_codec_dev_write(speaker, stereo, frames * 4) != ESP_CODEC_DEV_OK) return ESP_FAIL;
    playback_pending = true;
    playback_frames+=frames;
    return ESP_OK;
}
