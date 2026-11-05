#include "mochi_options.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "nvs.h"
#include <math.h>
#include <string.h>
#define OPTIONS_MAGIC 0x4d4f0701
static mochi_options_t options;
static portMUX_TYPE lock=portMUX_INITIALIZER_UNLOCKED;
static uint32_t revision,saved_revision;
static int64_t changed_at;
static StaticSemaphore_t save_mutex_buffer;
static SemaphoreHandle_t save_mutex;
void mochi_options_init(void)
{
    save_mutex=xSemaphoreCreateMutexStatic(&save_mutex_buffer);
    options=(mochi_options_t){.magic=OPTIONS_MAGIC,.name="Mochi",.cutoff=.9f,.arena_bytes=262144,.window=5,.microphone=true,.handsfree=true};
    mochi_options_t restored; nvs_handle_t handle; size_t size=sizeof(restored);
    if (nvs_open("mochi_voice",NVS_READONLY,&handle)==ESP_OK) {
        bool valid=nvs_get_blob(handle,"options",&restored,&size)==ESP_OK && size==sizeof(restored);
        nvs_close(handle);
        if (valid) mochi_options_set(&restored);
    }
    saved_revision=revision;
}
void mochi_options_get(mochi_options_t *out)
{
    portENTER_CRITICAL(&lock); *out=options; portEXIT_CRITICAL(&lock);
}
bool mochi_options_set(const mochi_options_t *v)
{
    if (!v || v->magic!=OPTIONS_MAGIC || !memchr(v->name,0,sizeof(v->name)) || !v->name[0] ||
        !memchr(v->model_id,0,sizeof(v->model_id)) || !memchr(v->pending_id,0,sizeof(v->pending_id)) ||
        !memchr(v->pending_name,0,sizeof(v->pending_name)) || !memchr(v->public_key,0,sizeof(v->public_key)) ||
        !isfinite(v->cutoff) || v->cutoff<=0 || v->cutoff>1 || !v->window || v->window>16 ||
        v->arena_bytes<32768 || v->arena_bytes>1048576 || v->slot>1 || v->power_mode>MOCHI_POWER_WALK) return false;
    portENTER_CRITICAL(&lock); options=*v; revision++; changed_at=esp_timer_get_time(); portEXIT_CRITICAL(&lock);
    return true;
}
void mochi_options_microphone(bool enabled)
{
    portENTER_CRITICAL(&lock);
    if(options.microphone!=enabled) { options.microphone=enabled; revision++; changed_at=esp_timer_get_time(); }
    portEXIT_CRITICAL(&lock);
}
void mochi_options_power(mochi_power_mode_t mode)
{
    if (mode>MOCHI_POWER_WALK) return;
    portENTER_CRITICAL(&lock);
    if(options.power_mode!=mode) { options.power_mode=mode; revision++; changed_at=esp_timer_get_time(); }
    portEXIT_CRITICAL(&lock);
}
bool mochi_options_flush(void)
{
    if (!save_mutex || xSemaphoreTake(save_mutex,pdMS_TO_TICKS(3000))!=pdTRUE) return false;
    mochi_options_t snapshot; uint32_t target; bool saved;
    portENTER_CRITICAL(&lock); snapshot=options; target=revision; saved=target==saved_revision; portEXIT_CRITICAL(&lock);
    if(saved) { xSemaphoreGive(save_mutex); return true; }
    nvs_handle_t handle;
    if (nvs_open("mochi_voice",NVS_READWRITE,&handle)!=ESP_OK) { xSemaphoreGive(save_mutex); return false; }
    esp_err_t error=nvs_set_blob(handle,"options",&snapshot,sizeof(snapshot));
    if (error==ESP_OK) error=nvs_commit(handle);
    nvs_close(handle);
    if (error==ESP_OK) { portENTER_CRITICAL(&lock); saved_revision=target; portEXIT_CRITICAL(&lock); }
    xSemaphoreGive(save_mutex);
    return error==ESP_OK;
}
void mochi_options_poll(void)
{
    portENTER_CRITICAL(&lock); bool save=revision!=saved_revision && esp_timer_get_time()-changed_at>=700000; portEXIT_CRITICAL(&lock);
    if (save) mochi_options_flush();
}
