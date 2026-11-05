#pragma once
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include "esp_err.h"

#define MOCHI_WIFI_MAX_NETWORKS 12
typedef enum {
    MOCHI_WIFI_IDLE, MOCHI_WIFI_SCANNING, MOCHI_WIFI_CONNECTING,
    MOCHI_WIFI_CONNECTED, MOCHI_WIFI_FAILED
} mochi_wifi_phase_t;
typedef enum {
    MOCHI_WIFI_ERROR_NONE, MOCHI_WIFI_ERROR_BUSY, MOCHI_WIFI_ERROR_INVALID,
    MOCHI_WIFI_ERROR_UNAVAILABLE, MOCHI_WIFI_ERROR_SCAN, MOCHI_WIFI_ERROR_AUTH,
    MOCHI_WIFI_ERROR_TIMEOUT, MOCHI_WIFI_ERROR_SAVE, MOCHI_WIFI_ERROR_CONNECT
} mochi_wifi_error_t;
typedef struct {
    char ssid[33];
    int8_t rssi;
    bool secured, current;
} mochi_wifi_network_t;
typedef struct {
    mochi_wifi_phase_t phase;
    mochi_wifi_error_t error;
    uint32_t revision;
    bool connected;
    uint8_t count;
    char current_ssid[33];
    mochi_wifi_network_t networks[MOCHI_WIFI_MAX_NETWORKS];
} mochi_wifi_status_t;

/* Enqueue work only; safe from the LVGL task. No password is returned. */
bool mochi_wifi_scan_start(void);
bool mochi_wifi_connect_start(const char *ssid, const char *password);
void mochi_wifi_get_status(mochi_wifi_status_t *out);
bool mochi_wifi_configuring(void);

void mochi_runtime_start(void);
bool mochi_runtime_reserve_audio(void);
void mochi_voice_start(void);
void mochi_voice_stop(void);
bool mochi_voice_busy(void);
bool mochi_voice_recording(void);
void mochi_voice_cancel(void);
bool mochi_voice_followup(void);
bool mochi_voice_test_wake_start(const char *path,float cutoff,unsigned window,uint32_t arena_bytes);
int mochi_voice_test_wake_result(void);
void mochi_voice_reload_model(void);
typedef esp_err_t (*mochi_download_sink_t)(const uint8_t *bytes,size_t size,void *context);
esp_err_t mochi_runtime_request(const char *route,const char *json,mochi_download_sink_t sink,void *context,
                              size_t limit,int *http_status);
esp_err_t mochi_runtime_request_with_timeout(const char *route,const char *json,mochi_download_sink_t sink,
                              void *context,size_t limit,int *http_status,uint32_t timeout_ms);
const char *mochi_runtime_device_id(void);
bool mochi_runtime_trusted_channel(void);
/* Approved, paired educational prompts. Does not accept arbitrary spoken text. */
bool mochi_runtime_education_cue(const char *cue);
/* Audio owner of an approved question/cue; never opens the microphone. */
bool mochi_runtime_education_narrating(void);
