#include "mochi_runtime.h"
#include "mochi_education.h"
#include "mochi_education_text.h"
#include "mochi_lessons.h"
#include "mochi.h"
#include "mochi_animation.h"
#include "mochi_audio.h"
#include "mochi_controls.h"
#include "mochi_gps.h"
#include "mochi_vpn.h"
#include "mochi_wifi_ui.h"
#include "mochi_options.h"
#include "mochi_wake.h"
#include "mochi_voice_policy.h"
#include "mochi_power_ui.h"
#include "mochi_display.h"
#include "mochi_resources.h"
#include "esp_ota_ops.h"
#include "esp_app_desc.h"
#include "mochi_dashboard.h"
#include "mochi_navigation.h"
#include <math.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "cJSON.h"
#include "driver/usb_serial_jtag.h"
#include "driver/usb_serial_jtag_vfs.h"
#include "esp_crt_bundle.h"
#include "esp_event.h"
#include "esp_heap_caps.h"
#include "esp_http_client.h"
#include "esp_log.h"
#include "esp_lv_adapter.h"
#include "esp_mac.h"
#include "esp_netif.h"
#include "esp_random.h"
#include "esp_sntp.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "nvs.h"
#include "nvs_flash.h"
#include "mbedtls/base64.h"

#define CONFIG_MAGIC 0x4d4f0200
#define WIFI_ALT_MAGIC 0x4d574601
#define MAX_RECORDING (MOCHI_SAMPLE_RATE * 8)
#define MAX_REPLY_BYTES (MOCHI_SAMPLE_RATE * 2 * 45)
static const char *TAG = "mochi_net";
static uint8_t *reply_buffer;
static SemaphoreHandle_t reply_buffer_lock;
static atomic_bool reply_buffer_ready;

bool mochi_runtime_reserve_audio(void)
{
    if(atomic_load(&reply_buffer_ready))return true;
    if(!reply_buffer)reply_buffer=heap_caps_malloc(MAX_REPLY_BYTES,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    if(!reply_buffer_lock)reply_buffer_lock=xSemaphoreCreateMutex();
    bool ready=reply_buffer && reply_buffer_lock;
    atomic_store(&reply_buffer_ready,ready);return ready;
}
static uint8_t *borrow_reply_buffer(void)
{
    return atomic_load(&reply_buffer_ready) && xSemaphoreTake(reply_buffer_lock,pdMS_TO_TICKS(1000))==pdTRUE?reply_buffer:NULL;
}
static void return_reply_buffer(uint8_t *bytes)
{
    if(bytes && bytes==reply_buffer)xSemaphoreGive(reply_buffer_lock);
}
typedef struct {
    uint32_t magic;
    char ssid[33], password[65], server_url[256], token[96];
} device_config_t;
static device_config_t config;
typedef struct {
    uint32_t magic;
    char ssid[33], password[65];
} alternate_wifi_t;
static alternate_wifi_t alternate_wifi;
static EventGroupHandle_t network;
static TaskHandle_t voice_task;
static TaskHandle_t wifi_worker;
static atomic_bool busy, recording;
static atomic_bool manual_requested,cancelled,followup_active,reload_model;
static atomic_bool stream_test_requested;
static atomic_bool stream_input_test_requested;
static atomic_bool sync_test_requested;
static atomic_bool education_speech_pending, education_narrating;
static atomic_uint education_prompt_retry_after_ms;
static atomic_int wake_test_result;
static struct { char path[80]; float cutoff; unsigned window; uint32_t arena; } wake_test;
static atomic_bool wake_test_requested;
static const char *turn_trigger="manual";
static char device_id[24];
static bool nvs_ready;
static atomic_int wifi_reason;
static atomic_bool wifi_scanning, wifi_using_alternate, wifi_has_alternate, wifi_working, wifi_control_ready;
static atomic_uint wifi_failures;
static portMUX_TYPE wifi_lock = portMUX_INITIALIZER_UNLOCKED;
static mochi_wifi_status_t wifi_status;
typedef struct {
    bool scan;
    char ssid[33], password[65];
} wifi_request_t;
static wifi_request_t wifi_request;
#define WIFI_DISCONNECTED_BIT BIT1
#define WIFI_GOT_IP_BIT BIT2
#define WIFI_WORK_REQUEST BIT0
#define WIFI_WORK_RECONNECT BIT1
static void check_weather(void);
static void check_server_audio(void);
static bool voice_errors_self_test(void);

static bool voice_interaction_blocked(void)
{
    return mochi_interaction_blocked() ||
        (mochi_education_active() && !mochi_education_voice_allowed());
}


static void secure_zero(void *buffer, size_t size)
{
    volatile unsigned char *bytes = buffer;
    while (size--) *bytes++ = 0;
}

/* Canonical decimal IPv4 only: no short forms, signs, octal or trailing text. */
static bool parse_ipv4(const char *text, uint8_t address[4], const char **end)
{
    if (!text) return false;
    const char *cursor = text;
    for (int i = 0; i < 4; i++) {
        if (*cursor < '0' || *cursor > '9' ||
            (*cursor == '0' && cursor[1] >= '0' && cursor[1] <= '9')) return false;
        unsigned value = 0, digits = 0;
        do {
            value = value * 10 + (*cursor++ - '0');
            if (++digits > 3 || value > 255) return false;
        } while (*cursor >= '0' && *cursor <= '9');
        address[i] = (uint8_t)value;
        if (i < 3 && *cursor++ != '.') return false;
    }
    *end = cursor;
    return true;
}

static bool overlay_address(const uint8_t address[4])
{
    return address[0] == 100 && address[1] >= 64 && address[1] <= 127;
}

static bool valid_peer_ip(const char *text)
{
    uint8_t address[4];
    const char *end;
    return parse_ipv4(text, address, &end) && !*end && overlay_address(address);
}

static bool http_url_ip(const char *url, uint8_t address[4])
{
    const char *end;
    if (strncmp(url, "http://", 7) || !parse_ipv4(url + 7, address, &end)) return false;
    if (*end == ':') {
        unsigned port = 0, digits = 0;
        end++;
        while (*end >= '0' && *end <= '9') {
            port = port * 10 + (*end++ - '0');
            if (++digits > 5 || port > 65535) return false;
        }
        if (!digits || !port) return false;
    }
    return !*end || *end == '/';
}

static bool server_url_policy(const char *url, bool vpn_configured)
{
    if (!url || !*url || strlen(url) >= sizeof(config.server_url) || strpbrk(url, "@#?\\")) return false;
    for (const unsigned char *c = (const unsigned char *)url; *c; c++) if (*c <= 32 || *c == 127) return false;
    if (!strncmp(url, "https://", 8)) return url[8] && url[8] != '/' && url[8] != ':';
    uint8_t address[4];
    if (!http_url_ip(url, address)) return false;
    return address[0] == 10 || (address[0] == 192 && address[1] == 168) ||
        (address[0] == 172 && address[1] >= 16 && address[1] <= 31) ||
        (overlay_address(address) && vpn_configured);
}

static bool safe_server(const char *url)
{
    return server_url_policy(url, mochi_vpn_configured());
}

static bool overlay_transport_allowed(bool needs_vpn, bool configured, bool ready)
{
    return !needs_vpn || (configured && ready);
}

static bool server_network_ready(void)
{
    uint8_t address[4];
    bool overlay = http_url_ip(config.server_url, address) && overlay_address(address);
    return (xEventGroupGetBits(network) & BIT0) && safe_server(config.server_url) &&
        overlay_transport_allowed(overlay, mochi_vpn_configured(), mochi_vpn_ready());
}

/* A ready snapshot alone is insufficient: the tunnel may disappear after it.
 * Binding the socket to WG also prevents falling back to the Wi-Fi route. */
static bool bind_server_transport(esp_http_client_config_t *options, struct ifreq *interface)
{
    uint8_t address[4];
    if (!http_url_ip(config.server_url, address) || !overlay_address(address)) return true;
    char peer[16];
    snprintf(peer, sizeof(peer), "%u.%u.%u.%u", address[0], address[1], address[2], address[3]);
    memset(interface, 0, sizeof(*interface));
    if (!mochi_vpn_bind_interface(peer, interface) || !interface->ifr_name[0]) return false;
    options->if_name = interface;
    return true;
}

static bool valid_wifi(const char *ssid, const char *password)
{
    if (!ssid || !password) return false;
    size_t name_size = strnlen(ssid, 33), password_size = strnlen(password, 65);
    if (!name_size || name_size > 32 || password_size > 64 ||
        (password_size && password_size < 8)) return false;
    for (const unsigned char *c = (const unsigned char *)ssid; *c; c++)
        if (*c < 32 || *c == 127) return false;
    /* The 64-byte form is a raw WPA PSK, not a 64-character passphrase. */
    if (password_size == 64) for (size_t i = 0; i < password_size; i++)
        if (!((password[i] >= '0' && password[i] <= '9') ||
              (password[i] >= 'a' && password[i] <= 'f') ||
              (password[i] >= 'A' && password[i] <= 'F'))) return false;
    return true;
}

static bool next_wifi_is_alternate(bool current, unsigned failures, bool has_alternate)
{
    return has_alternate && failures >= 3 ? !current : current;
}

static esp_err_t set_station_credentials(const char *ssid, const char *password)
{
    wifi_config_t station = {0};
    memcpy(station.sta.ssid, ssid, strnlen(ssid, 32));
    memcpy(station.sta.password, password, strnlen(password, 64));
    station.sta.threshold.authmode = password[0] ? WIFI_AUTH_WPA_PSK : WIFI_AUTH_OPEN;
    station.sta.scan_method = WIFI_ALL_CHANNEL_SCAN;
    esp_err_t error = esp_wifi_set_config(WIFI_IF_STA, &station);
    secure_zero(&station, sizeof(station));
    return error;
}

static esp_err_t set_wifi_credentials(bool use_alternate)
{
    return set_station_credentials(use_alternate ? alternate_wifi.ssid : config.ssid,
        use_alternate ? alternate_wifi.password : config.password);
}

bool mochi_wifi_configuring(void) { return atomic_load(&wifi_working); }

void mochi_wifi_get_status(mochi_wifi_status_t *out)
{
    if (!out) return;
    portENTER_CRITICAL(&wifi_lock);
    *out = wifi_status;
    portEXIT_CRITICAL(&wifi_lock);
}

static void wifi_publish_phase(mochi_wifi_phase_t phase, mochi_wifi_error_t error)
{
    portENTER_CRITICAL(&wifi_lock);
    wifi_status.phase = phase;
    wifi_status.error = error;
    wifi_status.revision++;
    portEXIT_CRITICAL(&wifi_lock);
}

static bool wifi_submit(bool scan, const char *ssid, const char *password)
{
    bool expected = false;
    if (!atomic_load(&wifi_control_ready) || !wifi_worker || mochi_controls_power_pending()) return false;
    if (!scan && !valid_wifi(ssid, password)) return false;
    /* This is also the voice gate: neither recording nor another configuration
     * transaction can start until the worker has finished or restored Wi-Fi. */
    if (!atomic_compare_exchange_strong(&busy, &expected, true)) return false;
    if (mochi_controls_power_pending()) { atomic_store(&busy, false); return false; }
    atomic_store(&wifi_working, true);
    portENTER_CRITICAL(&wifi_lock);
    memset(&wifi_request, 0, sizeof(wifi_request));
    wifi_request.scan = scan;
    if (!scan) {
        strlcpy(wifi_request.ssid, ssid, sizeof(wifi_request.ssid));
        strlcpy(wifi_request.password, password, sizeof(wifi_request.password));
    }
    wifi_status.phase = scan ? MOCHI_WIFI_SCANNING : MOCHI_WIFI_CONNECTING;
    wifi_status.error = MOCHI_WIFI_ERROR_NONE;
    wifi_status.revision++;
    portEXIT_CRITICAL(&wifi_lock);
    xTaskNotify(wifi_worker, WIFI_WORK_REQUEST, eSetBits);
    return true;
}

bool mochi_wifi_scan_start(void) { return wifi_submit(true, NULL, NULL); }
bool mochi_wifi_connect_start(const char *ssid, const char *password)
{
    return wifi_submit(false, ssid, password);
}

static void ui(mochi_state_t state, int duration)
{
    mochi_display_activity();
    if (esp_lv_adapter_lock(200) == ESP_OK) {
        mochi_set_state(state, duration);
        esp_lv_adapter_unlock();
    }
}

static void level(const int16_t *pcm, size_t frames)
{
    float energy = 0;
    for (size_t i = 0; i < frames; i++) energy += (float)pcm[i] * pcm[i];
    /* A block lasts 16 ms. Waiting up to 50 ms for the UI here can starve
     * I2S, cutting syllables or stretching the perceived spoken phrase. */
    mochi_set_audio_level(fminf(1, sqrtf(energy / frames) / 7000));
}

static atomic_bool navigation_speaking;
bool mochi_voice_busy(void) { return atomic_load(&busy); }
bool mochi_voice_recording(void) { return atomic_load(&recording); }
void mochi_voice_stop(void) {
    atomic_store(&recording, false);
    if(mochi_education_active())mochi_lessons_voice_end();
}
void mochi_voice_cancel(void) { atomic_store(&cancelled,true); atomic_store(&recording,false); }
bool mochi_voice_followup(void) { return atomic_load(&followup_active); }
void mochi_voice_reload_model(void) { atomic_store(&reload_model,true); }
bool mochi_voice_test_wake_start(const char *path,float cutoff,unsigned window,uint32_t arena_bytes)
{
    if (!path || strlen(path)>=sizeof(wake_test.path) || mochi_voice_busy() || wake_test_requested) return false;
    strlcpy(wake_test.path,path,sizeof(wake_test.path)); wake_test.cutoff=cutoff; wake_test.window=window; wake_test.arena=arena_bytes;
    atomic_store(&wake_test_result,0); atomic_store(&wake_test_requested,true); return true;
}
int mochi_voice_test_wake_result(void) { return atomic_load(&wake_test_result); }
void mochi_voice_start(void)
{
    if (mochi_education_active() && !mochi_education_voice_allowed()) {
        mochi_education_notice(mochi_education_policy_notice(), 5000);
        return;
    }
    if (mochi_voice_busy()) {
        if(atomic_load(&navigation_speaking)) {
            atomic_store(&cancelled,true); atomic_store(&manual_requested,true); atomic_store(&recording,true);
        } else mochi_voice_cancel();
        return;
    }
    if (!voice_task || mochi_controls_power_pending()) return;
    bool lesson_intent=mochi_education_active() && mochi_lessons_interacting();
    if(lesson_intent && !mochi_lessons_voice_begin())return;
    if(voice_interaction_blocked()){if(lesson_intent)mochi_lessons_voice_end();return;}
    mochi_options_t options; mochi_options_get(&options);
    if (!options.microphone) {if(lesson_intent)mochi_lessons_voice_end();return;}
    atomic_store(&cancelled,false);
    atomic_store(&manual_requested,true);
    atomic_store(&recording, true);
    xTaskNotifyGive(voice_task);
}

static void wifi_update_link(bool connected, const char *ssid, size_t length)
{
    portENTER_CRITICAL(&wifi_lock);
    wifi_status.connected = connected;
    memset(wifi_status.current_ssid, 0, sizeof(wifi_status.current_ssid));
    if (ssid && length <= 32) memcpy(wifi_status.current_ssid, ssid, length);
    for (unsigned i = 0; i < wifi_status.count; i++)
        wifi_status.networks[i].current = connected &&
            !strcmp(wifi_status.networks[i].ssid, wifi_status.current_ssid);
    wifi_status.revision++;
    portEXIT_CRITICAL(&wifi_lock);
}

/* Called only by the dedicated worker, never by LVGL or the Wi-Fi event loop. */
static void wifi_disconnect_and_drain(void)
{
    xEventGroupClearBits(network, WIFI_DISCONNECTED_BIT | WIFI_GOT_IP_BIT);
    if (esp_wifi_disconnect() == ESP_OK)
        xEventGroupWaitBits(network, WIFI_DISCONNECTED_BIT, pdTRUE, pdFALSE, pdMS_TO_TICKS(1200));
    xEventGroupClearBits(network, WIFI_DISCONNECTED_BIT | WIFI_GOT_IP_BIT);
}

static bool wifi_auth_failure(int reason)
{
    return reason == WIFI_REASON_AUTH_FAIL || reason == WIFI_REASON_HANDSHAKE_TIMEOUT ||
        reason == WIFI_REASON_4WAY_HANDSHAKE_TIMEOUT ||
        reason == WIFI_REASON_NO_AP_FOUND_W_COMPATIBLE_SECURITY ||
        reason == WIFI_REASON_NO_AP_FOUND_IN_AUTHMODE_THRESHOLD;
}

static void wifi_collect_networks(mochi_wifi_status_t *snapshot, const wifi_ap_record_t *aps, unsigned count)
{
    snapshot->count = 0;
    memset(snapshot->networks, 0, sizeof(snapshot->networks));
    for (unsigned i = 0; i < count; i++) {
        const wifi_ap_record_t *ap = &aps[i];
        if (!ap->ssid[0] || ap->primary < 1 || ap->primary > 14 ||
            strnlen((const char *)ap->ssid, sizeof(ap->ssid)) > 32) continue;
        bool secured = ap->authmode != WIFI_AUTH_OPEN;
        unsigned slot = snapshot->count;
        for (unsigned j = 0; j < snapshot->count; j++)
            if (!strcmp(snapshot->networks[j].ssid, (const char *)ap->ssid)) { slot = j; break; }
        if (slot < snapshot->count) {
            mochi_wifi_network_t *old = &snapshot->networks[slot];
            /* Prefer the protected AP if a name is advertised with both
             * security modes. Never suggest an automatic open downgrade. */
            if ((old->secured && !secured) || (old->secured == secured && old->rssi >= ap->rssi)) continue;
        } else if (snapshot->count < MOCHI_WIFI_MAX_NETWORKS) {
            snapshot->count++;
        } else {
            slot = 0;
            for (unsigned j = 1; j < snapshot->count; j++)
                if (snapshot->networks[j].rssi < snapshot->networks[slot].rssi) slot = j;
            if (snapshot->networks[slot].rssi >= ap->rssi) continue;
        }
        mochi_wifi_network_t *item = &snapshot->networks[slot];
        strlcpy(item->ssid, (const char *)ap->ssid, sizeof(item->ssid));
        item->rssi = ap->rssi;
        item->secured = secured;
        item->current = snapshot->connected && !strcmp(item->ssid, snapshot->current_ssid);
    }
    for (unsigned i = 1; i < snapshot->count; i++) {
        mochi_wifi_network_t item = snapshot->networks[i];
        unsigned j = i;
        while (j && snapshot->networks[j - 1].rssi < item.rssi) {
            snapshot->networks[j] = snapshot->networks[j - 1];
            j--;
        }
        snapshot->networks[j] = item;
    }
}

static void wifi_scan_worker(void)
{
    wifi_scan_config_t scan = {.show_hidden = true, .scan_type = WIFI_SCAN_TYPE_ACTIVE};
    scan.scan_time.active.min = 40;
    scan.scan_time.active.max = 120;
    atomic_store(&wifi_scanning, true);
    esp_err_t error = esp_wifi_scan_start(&scan, true);
    if (error == ESP_ERR_WIFI_STATE) {
        /* A reconnect attempt may already be running while outside home.
         * Pause that attempt to make a manual scan possible. */
        wifi_disconnect_and_drain();
        error = esp_wifi_scan_start(&scan, true);
    }
    uint16_t count = 48;
    wifi_ap_record_t *aps = heap_caps_calloc(count, sizeof(*aps), MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!aps) aps = calloc(count, sizeof(*aps));
    if (error == ESP_OK && aps) error = esp_wifi_scan_get_ap_records(&count, aps);
    else {
        esp_wifi_clear_ap_list();
        if (!aps) error = ESP_ERR_NO_MEM;
    }
    if (error != ESP_OK) esp_wifi_clear_ap_list();
    if (error == ESP_OK) {
        mochi_wifi_status_t snapshot;
        mochi_wifi_get_status(&snapshot);
        wifi_collect_networks(&snapshot, aps, count);
        portENTER_CRITICAL(&wifi_lock);
        wifi_status.count = snapshot.count;
        memcpy(wifi_status.networks, snapshot.networks, sizeof(wifi_status.networks));
        for (unsigned i = 0; i < wifi_status.count; i++)
            wifi_status.networks[i].current = wifi_status.connected &&
                !strcmp(wifi_status.networks[i].ssid, wifi_status.current_ssid);
        portEXIT_CRITICAL(&wifi_lock);
        wifi_publish_phase(MOCHI_WIFI_IDLE, MOCHI_WIFI_ERROR_NONE);
    } else wifi_publish_phase(MOCHI_WIFI_FAILED, MOCHI_WIFI_ERROR_SCAN);
    free(aps);
}

static bool wifi_store_selection(const alternate_wifi_t *next, bool use_alternate)
{
    nvs_handle_t handle;
    if (!nvs_ready || nvs_open("mochi_wifi", NVS_READWRITE, &handle) != ESP_OK) return false;
    esp_err_t error = next ? nvs_set_blob(handle, "alt", next, sizeof(*next)) : ESP_OK;
    if (error == ESP_OK) error = nvs_set_u8(handle, "preferred", use_alternate ? 1 : 0);
    if (error == ESP_OK) error = nvs_commit(handle);
    nvs_close(handle);
    return error == ESP_OK;
}

static void wifi_connect_worker(const wifi_request_t *request)
{
    bool previous = atomic_load(&wifi_using_alternate);
    mochi_wifi_error_t failure = MOCHI_WIFI_ERROR_CONNECT;
    wifi_disconnect_and_drain();
    if (set_station_credentials(request->ssid, request->password) != ESP_OK || esp_wifi_connect() != ESP_OK)
        goto restore;
    TickType_t began = xTaskGetTickCount();
    unsigned retries = 0;
    while (xTaskGetTickCount() - began < pdMS_TO_TICKS(25000)) {
        EventBits_t bits = xEventGroupWaitBits(network, WIFI_GOT_IP_BIT | WIFI_DISCONNECTED_BIT,
            pdTRUE, pdFALSE, pdMS_TO_TICKS(250));
        if (bits & WIFI_GOT_IP_BIT) {
            wifi_ap_record_t ap = {0};
            bool correct = esp_wifi_sta_get_ap_info(&ap) == ESP_OK &&
                !strcmp((const char *)ap.ssid, request->ssid) &&
                (!request->password[0] || ap.authmode != WIFI_AUTH_OPEN);
            if (correct && (xEventGroupGetBits(network) & BIT0)) {
                bool original = !strcmp(config.ssid, request->ssid) && !strcmp(config.password, request->password);
                bool existing = alternate_wifi.magic == WIFI_ALT_MAGIC &&
                    !strcmp(alternate_wifi.ssid, request->ssid) && !strcmp(alternate_wifi.password, request->password);
                if (!original && !existing) {
                    alternate_wifi_t next = {.magic = WIFI_ALT_MAGIC};
                    strlcpy(next.ssid, request->ssid, sizeof(next.ssid));
                    strlcpy(next.password, request->password, sizeof(next.password));
                    bool saved = wifi_store_selection(&next, true);
                    if (saved) {
                        alternate_wifi = next;
                        atomic_store(&wifi_has_alternate, true);
                    }
                    secure_zero(&next, sizeof(next));
                    if (!saved) { failure = MOCHI_WIFI_ERROR_SAVE; goto restore; }
                } else if (!wifi_store_selection(NULL, !original)) {
                    failure = MOCHI_WIFI_ERROR_SAVE;
                    goto restore;
                }
                atomic_store(&wifi_using_alternate, !original);
                atomic_store(&wifi_failures, 0);
                wifi_publish_phase(MOCHI_WIFI_CONNECTED, MOCHI_WIFI_ERROR_NONE);
                return;
            }
        }
        if (bits & WIFI_DISCONNECTED_BIT) {
            if (wifi_auth_failure(atomic_load(&wifi_reason))) { failure = MOCHI_WIFI_ERROR_AUTH; goto restore; }
            if (++retries >= 3 || esp_wifi_connect() != ESP_OK) goto restore;
        }
    }
    failure = MOCHI_WIFI_ERROR_TIMEOUT;
restore:
    /* Retain both persistent networks on every failed attempt, including an
     * NVS failure after receiving an IP. Voice/VPN credentials are untouched. */
    wifi_disconnect_and_drain();
    set_wifi_credentials(previous);
    atomic_store(&wifi_using_alternate, previous);
    atomic_store(&wifi_failures, 0);
    wifi_publish_phase(MOCHI_WIFI_FAILED, failure);
}

static void wifi_worker_task(void *argument)
{
    (void)argument;
    for (;;) {
        uint32_t pending = 0;
        xTaskNotifyWait(0, UINT32_MAX, &pending, portMAX_DELAY);
        if (pending & WIFI_WORK_REQUEST) {
            wifi_request_t request;
            portENTER_CRITICAL(&wifi_lock);
            request = wifi_request;
            secure_zero(&wifi_request, sizeof(wifi_request));
            portEXIT_CRITICAL(&wifi_lock);
            if (request.scan) wifi_scan_worker();
            else wifi_connect_worker(&request);
            secure_zero(&request, sizeof(request));
            atomic_store(&wifi_scanning, false);
            atomic_store(&wifi_working, false);
            /* Explicit attempts suppress the normal fallback. Resume the
             * selected saved network only after the transaction ends. */
            if (!(xEventGroupGetBits(network) & BIT0)) esp_wifi_connect();
            atomic_store(&busy, false);
        } else if ((pending & WIFI_WORK_RECONNECT) && !atomic_load(&wifi_working) &&
                   !(xEventGroupGetBits(network) & BIT0)) {
            /* Keep all driver connect/configure calls out of the event task. */
            bool current = atomic_load(&wifi_using_alternate);
            bool next = next_wifi_is_alternate(current, wifi_failures, alternate_wifi.magic == WIFI_ALT_MAGIC);
            if (next != current && set_wifi_credentials(next) == ESP_OK) {
                atomic_store(&wifi_using_alternate, next);
                wifi_failures = 0;
            }
            esp_wifi_connect();
        }
    }
}

static void wifi_event(void *argument, esp_event_base_t base, int32_t id, void *data)
{
    (void)argument;
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START && wifi_worker)
        xTaskNotify(wifi_worker, WIFI_WORK_RECONNECT, eSetBits);
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        wifi_event_sta_disconnected_t *event = data;
        atomic_store(&wifi_reason, event ? event->reason : 0);
        xEventGroupClearBits(network, BIT0);
        wifi_update_link(false, NULL, 0);
        xEventGroupSetBits(network, WIFI_DISCONNECTED_BIT);
        if (!atomic_load(&wifi_scanning) && !atomic_load(&wifi_working)) {
            if (wifi_failures < 3) wifi_failures++;
            if (wifi_worker) xTaskNotify(wifi_worker, WIFI_WORK_RECONNECT, eSetBits);
        }
    }
    if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        xEventGroupSetBits(network, BIT0);
        xEventGroupSetBits(network, WIFI_GOT_IP_BIT);
        wifi_ap_record_t ap = {0};
        if (esp_wifi_sta_get_ap_info(&ap) == ESP_OK)
            wifi_update_link(true, (const char *)ap.ssid, strnlen((const char *)ap.ssid, 32));
        atomic_store(&wifi_reason, 0);
        wifi_failures = 0;
        mochi_vpn_start();
        ESP_LOGI(TAG, "Wi-Fi connected");
    }
}

static bool store_device_config(const device_config_t *next)
{
    nvs_handle_t handle;
    if (!nvs_ready || nvs_open("mochi", NVS_READWRITE, &handle) != ESP_OK) return false;
    esp_err_t error = nvs_set_blob(handle, "config", next, sizeof(*next));
    if (error == ESP_OK) error = nvs_commit(handle);
    nvs_close(handle);
    return error == ESP_OK;
}

static bool save_config(cJSON *json)
{
    device_config_t next = {.magic = CONFIG_MAGIC};
    bool saved = false;
    const char *names[] = {"ssid", "password", "server_url", "token"};
    char *destinations[] = {next.ssid, next.password, next.server_url, next.token};
    size_t sizes[] = {sizeof(next.ssid), sizeof(next.password), sizeof(next.server_url), sizeof(next.token)};
    for (int i = 0; i < 4; i++) {
        cJSON *value = cJSON_GetObjectItemCaseSensitive(json, names[i]);
        if (!cJSON_IsString(value) || strlen(value->valuestring) >= sizes[i]) goto done;
        memcpy(destinations[i], value->valuestring, strlen(value->valuestring) + 1);
    }
    size_t length = strlen(next.server_url);
    while (length && next.server_url[length - 1] == '/') next.server_url[--length] = 0;
    if (!valid_wifi(next.ssid, next.password) || strlen(next.token) < 32 || !safe_server(next.server_url)) goto done;
    saved = store_device_config(&next);
done:
    secure_zero(&next, sizeof(next));
    return saved;
}

static bool valid_auth_key(const char *key)
{
    size_t size = strlen(key);
    if (size < 32 || size > 127 || strncmp(key, "tskey-auth-", 11)) return false;
    for (const unsigned char *c = (const unsigned char *)key; *c; c++)
        if (!((*c >= 'A' && *c <= 'Z') || (*c >= 'a' && *c <= 'z') ||
              (*c >= '0' && *c <= '9') || *c == '-' || *c == '_')) return false;
    return true;
}

static bool save_vpn_config(cJSON *json)
{
    device_config_t next = config;
    alternate_wifi_t alternate = {.magic = WIFI_ALT_MAGIC};
    bool saved = false;
    cJSON *key = cJSON_GetObjectItemCaseSensitive(json, "auth_key");
    cJSON *peer = cJSON_GetObjectItemCaseSensitive(json, "peer_ip");
    cJSON *ssid = cJSON_GetObjectItemCaseSensitive(json, "hotspot_ssid");
    cJSON *password = cJSON_GetObjectItemCaseSensitive(json, "hotspot_password");
    if (!nvs_ready || next.magic != CONFIG_MAGIC ||
        !next.ssid[0] || strlen(next.token) < 32 || !cJSON_IsString(key) ||
        !valid_auth_key(key->valuestring) || !cJSON_IsString(peer) || !valid_peer_ip(peer->valuestring)) goto done;
    if (ssid || password) {
        if (!cJSON_IsString(ssid) || !cJSON_IsString(password) ||
            !valid_wifi(ssid->valuestring, password->valuestring) || !password->valuestring[0]) goto done;
        strlcpy(alternate.ssid, ssid->valuestring, sizeof(alternate.ssid));
        strlcpy(alternate.password, password->valuestring, sizeof(alternate.password));
    }
    snprintf(next.server_url, sizeof(next.server_url), "http://%s:8765", peer->valuestring);
    /* Validate every field before the first persistent write. configure() saves
     * VPN credentials but changes no active session until the ensuing restart. */
    if (!mochi_vpn_configure(key->valuestring, peer->valuestring)) goto done;
    if (ssid) {
        nvs_handle_t handle;
        if (nvs_open("mochi_wifi", NVS_READWRITE, &handle) != ESP_OK) goto done;
        esp_err_t error = nvs_set_blob(handle, "alt", &alternate, sizeof(alternate));
        if (error == ESP_OK) error = nvs_commit(handle);
        nvs_close(handle);
        if (error != ESP_OK) goto done;
    }
    /* Preserve the original Wi-Fi and voice token byte for byte. */
    saved = store_device_config(&next);
done:
    secure_zero(&next, sizeof(next));
    secure_zero(&alternate, sizeof(alternate));
    return saved;
}

static void erase_json_secret(cJSON *json, const char *name)
{
    cJSON *item = cJSON_GetObjectItemCaseSensitive(json, name);
    if (cJSON_IsString(item)) secure_zero(item->valuestring, strlen(item->valuestring));
}

/* Parser/policy tests never change the live VPN, Wi-Fi, GPS or NVS state. */
static bool vpn_policy_self_test(void)
{
    return valid_peer_ip("100.64.0.1") && valid_peer_ip("100.127.255.254") &&
        !valid_peer_ip("100.63.255.255") && !valid_peer_ip("100.128.0.1") &&
        !valid_peer_ip("100.064.0.1") && !valid_peer_ip("100.64.1") &&
        !valid_peer_ip("100.64.0.1.attacker") && !valid_peer_ip("100.64.0.1:8765") &&
        server_url_policy("http://100.64.0.1:8765", true) &&
        !server_url_policy("http://100.64.0.1:8765", false) &&
        !server_url_policy("http://100.64.0.1:999999", true) &&
        !server_url_policy("http://100.64.0.1:0", true) &&
        !server_url_policy("http://100.64.0.1@attacker", true) &&
        !server_url_policy("http://100.64.0.1\\attacker", true) &&
        !server_url_policy("http://100.64.0.1:8765\r\nAuthorization:x", true) &&
        !server_url_policy("http://8.8.8.8:8765", true) &&
        server_url_policy("http://192.168.8.245:8765", false) &&
        server_url_policy("https://example.com", false) &&
        overlay_transport_allowed(false, false, false) &&
        !overlay_transport_allowed(true, false, true) &&
        !overlay_transport_allowed(true, true, false) &&
        overlay_transport_allowed(true, true, true) &&
        valid_auth_key("tskey-auth-abcdefghijklmnopqrstuvwxyz") &&
        !valid_auth_key("tskey-auth-short") && !valid_auth_key("tskey-api-abcdefghijklmnopqrstuvwxyz") &&
        valid_wifi("iPhone", "12345678") && !valid_wifi("", "12345678") &&
        !valid_wifi("iPhone", "short") &&
        !next_wifi_is_alternate(false, 2, true) && next_wifi_is_alternate(false, 3, true) &&
        !next_wifi_is_alternate(true, 3, true) && !next_wifi_is_alternate(false, 3, false);
}

/* Pure parser/list policy checks: no driver calls, scans, NVS or credentials. */
static bool wifi_policy_self_test(void)
{
    char max_ssid[34], hex_psk[65], bad_psk[65];
    memset(max_ssid, 'x', sizeof(max_ssid));
    max_ssid[32] = 0;
    memset(hex_psk, 'a', 64); hex_psk[64] = 0;
    memset(bad_psk, 'z', 64); bad_psk[64] = 0;
    if (!valid_wifi("Mi red", "") || !valid_wifi("Mi red", "12345678") ||
        !valid_wifi("iPhone de Mochi", hex_psk) || !valid_wifi(max_ssid, "12345678") ||
        valid_wifi("Mi red", bad_psk) || valid_wifi("", "12345678") ||
        valid_wifi("Mi red", "short") || valid_wifi("red\n", "12345678") ||
        valid_wifi(NULL, "12345678") || valid_wifi("red", NULL)) return false;
    max_ssid[32] = 'x'; max_ssid[33] = 0;
    if (valid_wifi(max_ssid, "12345678")) return false;
    wifi_ap_record_t aps[16] = {0};
    mochi_wifi_status_t snapshot = {.connected = true};
    strlcpy(snapshot.current_ssid, "red-00", sizeof(snapshot.current_ssid));
    for (unsigned i = 0; i < 14; i++) {
        snprintf((char *)aps[i].ssid, sizeof(aps[i].ssid), "red-%02u", i);
        aps[i].primary = 6;
        aps[i].rssi = -40 - i;
        aps[i].authmode = WIFI_AUTH_WPA2_PSK;
    }
    strlcpy((char *)aps[14].ssid, "red-00", sizeof(aps[14].ssid));
    aps[14].primary = 6; aps[14].rssi = -15; aps[14].authmode = WIFI_AUTH_OPEN;
    aps[15].primary = 6; /* An unnamed hidden network is entered manually. */
    wifi_collect_networks(&snapshot, aps, 16);
    if (snapshot.count != MOCHI_WIFI_MAX_NETWORKS || !snapshot.networks[0].current ||
        strcmp(snapshot.networks[0].ssid, "red-00") || !snapshot.networks[0].secured ||
        snapshot.networks[0].rssi != -40 ||
        !wifi_auth_failure(WIFI_REASON_AUTH_FAIL) || wifi_auth_failure(WIFI_REASON_NO_AP_FOUND)) return false;
    for (unsigned i = 1; i < snapshot.count; i++)
        if (snapshot.networks[i].rssi > snapshot.networks[i - 1].rssi) return false;
    return true;
}

/* Local USB diagnostic only: each complete row is independently identifiable,
 * so normal application logs cannot be mistaken for pixels. No network access. */
static void capture_frame(void)
{
    lv_draw_buf_t snapshot,*image=NULL;
    bool expected=false;
    if(mochi_voice_followup() || !atomic_compare_exchange_strong(&busy,&expected,true))return;
    uint8_t *storage=borrow_reply_buffer();
    if(!storage || mochi_voice_followup()){
        return_reply_buffer(storage);atomic_store(&busy,false);return;
    }
    if (esp_lv_adapter_lock(1000) == ESP_OK) {
        uint8_t *aligned=lv_draw_buf_align(storage,LV_COLOR_FORMAT_RGB565);
        if(lv_draw_buf_init(&snapshot,466,466,LV_COLOR_FORMAT_RGB565,0,aligned,MAX_REPLY_BYTES-(aligned-storage))==LV_RESULT_OK){
            lv_draw_buf_set_flag(&snapshot,LV_IMAGE_FLAGS_MODIFIABLE);
            if(lv_snapshot_take_to_draw_buf(lv_screen_active(),LV_COLOR_FORMAT_RGB565,&snapshot)==LV_RESULT_OK)image=&snapshot;
        }
        esp_lv_adapter_unlock();
    }
    if (!image || image->header.w > 466 || image->header.h > 466) {
        return_reply_buffer(storage);atomic_store(&busy,false);
        printf("@mochi_frame error\n");
        fflush(stdout);
        return;
    }
    flockfile(stdout);
    printf("@mochi_frame %u %u\n", (unsigned)image->header.w, (unsigned)image->header.h);
    fflush(stdout);
    static const char hex[] = "0123456789abcdef";
    char row[1900];
    for (unsigned y = 0; y < image->header.h; y++) {
        int used = snprintf(row, sizeof(row), "@mochi_row %u ", y);
        const uint8_t *pixels = image->data + y * image->header.stride;
        for (unsigned x = 0; x < image->header.w * 2; x++) {
            row[used++] = hex[pixels[x] >> 4];
            row[used++] = hex[pixels[x] & 15];
        }
        row[used++] = '\n';
        int sent = 0;
        while (sent < used) {
            int written = usb_serial_jtag_write_bytes(row + sent, used - sent, pdMS_TO_TICKS(1000));
            if (written <= 0) goto done;
            sent += written;
        }
    }
done:
    return_reply_buffer(storage);atomic_store(&busy,false);
    printf("@mochi_frame_end\n");
    fflush(stdout);
    funlockfile(stdout);
}

static void diagnose_wifi(void)
{
    mochi_wifi_status_t snapshot;
    mochi_wifi_get_status(&snapshot);
    printf("@mochi_wifi configured=%d connected=%d phase=%d error=%d working=%d reason=%d networks=%u alternate=%d active_alt=%d\n",
        config.magic == CONFIG_MAGIC, snapshot.connected, snapshot.phase, snapshot.error,
        mochi_wifi_configuring(), atomic_load(&wifi_reason), snapshot.count,
        atomic_load(&wifi_has_alternate), atomic_load(&wifi_using_alternate));
    fflush(stdout);
}

/* Explicit USB recovery test only. Use the same asynchronous path as the UI,
 * without reading or disclosing a password and without inventing an SSID. */
static bool wifi_recovery_test_start(void)
{
    mochi_wifi_status_t snapshot;
    mochi_wifi_get_status(&snapshot);
    if (config.magic != CONFIG_MAGIC || !snapshot.connected ||
        !(xEventGroupGetBits(network) & BIT0) || mochi_voice_busy() ||
        mochi_wifi_configuring() || mochi_wifi_ui_is_open() ||
        atomic_load(&wifi_using_alternate) || strcmp(snapshot.current_ssid, config.ssid)) return false;
    uint8_t random[16];
    char password[33];
    static const char hex[] = "0123456789abcdef";
    esp_fill_random(random, sizeof(random));
    for (unsigned i = 0; i < sizeof(random); i++) {
        password[i * 2] = hex[random[i] >> 4];
        password[i * 2 + 1] = hex[random[i] & 15];
    }
    password[32] = 0;
    if (!strcmp(password, config.password)) password[0] = password[0] == '0' ? '1' : '0';
    bool accepted = mochi_wifi_connect_start(config.ssid, password);
    secure_zero(password, sizeof(password));
    secure_zero(random, sizeof(random));
    return accepted;
}

static void check_server(void)
{
    if(mochi_voice_busy()){
        printf("@mochi_server ready=0 busy=1\n");fflush(stdout);return;
    }
    if (!server_network_ready()) {
        printf("@mochi_server ready=0 network_unavailable\n");
        fflush(stdout);
        return;
    }
    char url[288], authorization[112], response[2048];
    snprintf(url, sizeof(url), "%s/health", config.server_url);
    esp_http_client_config_t options = {.url = url, .timeout_ms = 10000,
        .crt_bundle_attach = esp_crt_bundle_attach, .disable_auto_redirect = true};
    struct ifreq interface;
    if (!bind_server_transport(&options, &interface)) {
        printf("@mochi_server ready=0 vpn_unavailable\n");
        fflush(stdout);
        return;
    }
    snprintf(authorization, sizeof(authorization), "Bearer %s", config.token);
    esp_http_client_handle_t client = esp_http_client_init(&options);
    int status = 0, size = 0;
    bool ready = false;
    if (client) {
        esp_http_client_set_header(client, "Authorization", authorization);
        if (esp_http_client_open(client, 0) == ESP_OK && esp_http_client_fetch_headers(client) >= 0) {
            status = esp_http_client_get_status_code(client);
            size = esp_http_client_read_response(client, response, sizeof(response) - 1);
            if (size > 0) {
                response[size] = 0;
                cJSON *json = cJSON_Parse(response);
                cJSON *provider = cJSON_GetObjectItemCaseSensitive(json, "provider");
                cJSON *profile = cJSON_GetObjectItemCaseSensitive(json, "profile");
                ready = status == 200 && cJSON_IsString(provider) && !strcmp(provider->valuestring, "hermes") &&
                    cJSON_IsString(profile) && !strcmp(profile->valuestring, "mochi") &&
                    cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(json, "profile_ready")) &&
                    cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(json, "voice_installed"));
                cJSON_Delete(json);
            }
        }
        esp_http_client_cleanup(client);
    }
    memset(authorization, 0, sizeof(authorization));
    printf("@mochi_server http=%d ready=%d\n", status, ready);
    fflush(stdout);
    if (ready && esp_lv_adapter_lock(200) == ESP_OK) {
        mochi_show_notice("Lista para hablar", 3500);
        esp_lv_adapter_unlock();
    }
}

static void console(void *argument)
{
    (void)argument;
    usb_serial_jtag_driver_config_t driver = {.tx_buffer_size = 4096, .rx_buffer_size = 4096};
    if (usb_serial_jtag_driver_install(&driver) != ESP_OK) {
        ESP_LOGE(TAG, "USB configuration interface unavailable");
        vTaskDelete(NULL);
    }
    usb_serial_jtag_vfs_use_driver();
    char line[1200];
    size_t used = 0;
    bool overflow = false;
    while (true) {
        uint8_t ch;
        if (usb_serial_jtag_read_bytes(&ch, 1, pdMS_TO_TICKS(100)) <= 0) {
            mochi_animation_upload_poll(); continue;
        }
        if (ch == '\r') continue;
        if (ch != '\n') {
            if (used < sizeof(line) - 1 && !overflow) line[used++] = ch;
            else overflow = true;
            continue;
        }
        line[used] = 0;
        if (!overflow && mochi_animation_console(line)) {
            /* Mochi's artwork transport is bounded to the compiled catalog. */
        } else if (!overflow && !strncmp(line, "@config ", 8)) {
            cJSON *json = cJSON_Parse(line + 8);
            bool expected = false;
            bool claimed = atomic_compare_exchange_strong(&busy, &expected, true);
            bool saved = claimed && json && save_config(json);
            erase_json_secret(json, "password");
            erase_json_secret(json, "token");
            cJSON_Delete(json);
            secure_zero(line, sizeof(line));
            printf("@mochi_config %s\n", saved ? "ok" : "invalid");
            fflush(stdout);
            if (saved) { vTaskDelay(pdMS_TO_TICKS(250)); esp_restart(); }
            if (claimed) atomic_store(&busy, false);
        } else if (!overflow && !strncmp(line, "@vpn-config ", 12)) {
            cJSON *json = cJSON_ParseWithOpts(line + 12, NULL, true);
            bool expected = false;
            bool claimed = atomic_compare_exchange_strong(&busy, &expected, true);
            bool saved = claimed && cJSON_IsObject(json) && save_vpn_config(json);
            erase_json_secret(json, "auth_key");
            erase_json_secret(json, "hotspot_password");
            cJSON_Delete(json);
            secure_zero(line, sizeof(line));
            printf("@mochi_vpn_config %s\n", saved ? "ok" : "invalid");
            fflush(stdout);
            if (saved) { vTaskDelay(pdMS_TO_TICKS(250)); esp_restart(); }
            if (claimed) atomic_store(&busy, false);
        } else if (!overflow && !strcmp(line, "@vpn")) {
            mochi_vpn_diagnose();
        } else if (!overflow && !strcmp(line, "@vpn-test")) {
            printf("@mochi_vpn_test %s\n", vpn_policy_self_test() && mochi_vpn_self_test() ? "PASS" : "FAIL");
            fflush(stdout);
        } else if (!overflow && !strcmp(line, "@status")) {
            printf("@mochi_status configured=%d wifi=%d busy=%d reason=%d\n", config.magic == CONFIG_MAGIC,
                    !!(xEventGroupGetBits(network) & BIT0), mochi_voice_busy(), wifi_reason);
            fflush(stdout);
        } else if (!overflow && !strcmp(line, "@audio")) {
            mochi_audio_diagnose();
        } else if (!overflow && !strcmp(line,"@power-ui")) {
            if (esp_lv_adapter_lock(200)==ESP_OK) {
                mochi_power_ui_diagnose();esp_lv_adapter_unlock();
            }
        } else if (!overflow && !strcmp(line,"@display")) { mochi_display_diagnose();
        } else if (!overflow && !strcmp(line,"@display-test")) {
            printf("@mochi_display_test %s\n",!mochi_voice_busy() && mochi_display_test()?"PASS":"FAIL"); fflush(stdout);
        } else if (!overflow && !strcmp(line,"@wake")) { mochi_wake_diagnose();
        } else if (!overflow && !strncmp(line,"@wake-prepare ",14)) {
            printf("@mochi_wake_prepare %s\n",mochi_resources_prepare_name(line+14)?"queued":"busy_or_invalid"); fflush(stdout);
        } else if (!overflow && !strcmp(line,"@wake-test")) {
            printf("@mochi_wake_test %s\n",mochi_resources_test_candidate()?"queued":"not_ready"); fflush(stdout);
        } else if (!overflow && !strcmp(line,"@voice-policy-test")) { printf("@mochi_voice_policy_test %s\n",mochi_voice_policy_self_test()?"PASS":"FAIL"); fflush(stdout);
        } else if (!overflow && !strcmp(line,"@resources")) { mochi_resources_diagnose();
        } else if (!overflow && !strcmp(line,"@firmware")) {
            const esp_partition_t *part=esp_ota_get_running_partition(); esp_ota_img_states_t state=ESP_OTA_IMG_UNDEFINED;
            if (part) esp_ota_get_state_partition(part,&state);
            printf("@mochi_firmware version=%s character=Mochi slot=%s address=0x%lx state=%d\n",esp_app_get_description()->version,part?part->label:"unknown",part?(unsigned long)part->address:0,state); fflush(stdout);
        } else if (!overflow && !strcmp(line,"@restart")) {
            if(!mochi_voice_busy()) { printf("@mochi_restart queued\n");fflush(stdout);vTaskDelay(pdMS_TO_TICKS(200));esp_restart(); }
            else { printf("@mochi_restart busy\n");fflush(stdout); }
        } else if (!overflow && !strcmp(line,"@ota-update")) { printf("@mochi_ota_request %s\n",mochi_resources_update()?"queued":"busy"); fflush(stdout);
        } else if (!overflow && !strcmp(line,"@resources-init")) { printf("@mochi_resources_init %s\n",mochi_resources_format()?"PASS":"FAIL"); fflush(stdout);
        } else if (!overflow && !strcmp(line,"@gps-request")) { mochi_gps_request();
        } else if (!overflow && !strcmp(line,"@personalize")) {
            if(esp_lv_adapter_lock(200)==ESP_OK){mochi_dashboard_diagnose();esp_lv_adapter_unlock();fflush(stdout);}
        } else if (!overflow && !strncmp(line,"@ui-pointer ",12)) {
            int x,y,pressed;char tail;bool ok=false;
            if(sscanf(line+12,"%d %d %d %c",&x,&y,&pressed,&tail)==3 && (pressed==0||pressed==1) && esp_lv_adapter_lock(200)==ESP_OK){
                ok=mochi_education_pointer(x,y,pressed) || mochi_navigation_pointer(x,y,pressed) || mochi_dashboard_pointer(x,y,pressed);esp_lv_adapter_unlock();
            }
            printf("@mochi_ui_pointer %s\n",ok?"ok":"invalid");fflush(stdout);
        } else if (!overflow && !strcmp(line,"@navigation")) { mochi_navigation_diagnose();
        } else if (!overflow && !strcmp(line,"@navigation-test")) { printf("@mochi_navigation_test %s\n",mochi_navigation_test()?"PASS":"FAIL"); fflush(stdout);
        } else if (!overflow && !strncmp(line,"@navigation-simulation ",23)) {
            double latitude=0,longitude=0; char extra;
            bool off=!strcmp(line+23,"off"),lost=!strcmp(line+23,"lost");
            bool ok=lost || ((off || sscanf(line+23,"%lf %lf %c",&latitude,&longitude,&extra)==2) && mochi_navigation_simulation(!off,latitude,longitude));
            if(lost) mochi_navigation_simulation_lost();
            printf("@mochi_navigation_simulation %s\n",ok?"ok":"invalid"); fflush(stdout);
        } else if (!overflow && !strncmp(line,"@navigation-session ",20)) { mochi_navigation_session(line+20);
        } else if (!overflow && !strncmp(line,"@dashboard ",11)) {
            if (esp_lv_adapter_lock(200)==ESP_OK) { mochi_dashboard_show((unsigned)atoi(line+11)); esp_lv_adapter_unlock(); }
        } else if (!overflow && !strcmp(line, "@audio-test")) {
            printf("@mochi_audio_test %s\n", mochi_audio_self_test() ? "PASS" : "FAIL");
            fflush(stdout);
        } else if (!overflow && !strncmp(line, "@emote ", 7)) {
            if (!mochi_voice_busy()) ui(mochi_state_from_name(line + 7), 3500);
        } else if (!overflow && !strcmp(line, "@frame")) {
            capture_frame();
        } else if (!overflow && !strcmp(line, "@wifi")) {
            diagnose_wifi();
        } else if (!overflow && !strcmp(line, "@wifi-scan")) {
            printf("@mochi_wifi_scan accepted=%d\n", mochi_wifi_scan_start());
            fflush(stdout);
        } else if (!overflow && (!strcmp(line, "@wifi-radio off") || !strcmp(line, "@wifi-radio on"))) {
            /* USB diagnostic: stop the real radio without changing stored networks.
             * Reboot also restores normal Wi-Fi startup if a test is interrupted. */
            bool enable = !strcmp(line, "@wifi-radio on");
            esp_err_t radio_result = mochi_voice_busy() ? ESP_ERR_INVALID_STATE :
                (enable ? esp_wifi_start() : esp_wifi_stop());
            printf("@mochi_wifi_radio enabled=%d result=%s\n", enable, esp_err_to_name(radio_result));
            fflush(stdout);
        } else if (!overflow && !strcmp(line, "@wifi-test")) {
            printf("@mochi_wifi_test %s\n", wifi_policy_self_test() ? "PASS" : "FAIL");
            fflush(stdout);
        } else if (!overflow && !strcmp(line, "@wifi-recovery-test")) {
            printf("@mochi_wifi_recovery_test accepted=%d\n", wifi_recovery_test_start());
            fflush(stdout);
        } else if (!overflow && !strncmp(line, "@wifi-ui ", 9)) {
            if (esp_lv_adapter_lock(200) == ESP_OK) {
                mochi_wifi_ui_preview(line + 9);
                esp_lv_adapter_unlock();
            }
        } else if (!overflow && !strcmp(line, "@server")) {
            check_server();
        } else if (!overflow && !strcmp(line, "@server-audio")) {
            check_server_audio();
        } else if (!overflow && !strcmp(line, "@av-test")) {
            atomic_store(&sync_test_requested,true);
            if (voice_task) xTaskNotifyGive(voice_task);
        } else if (!overflow && !strcmp(line,"@mic-speaker-test")) {
            atomic_store(&stream_input_test_requested,true);
            atomic_store(&stream_test_requested,true);
            if(voice_task)xTaskNotifyGive(voice_task);
        } else if (!overflow && !strcmp(line, "@speaker-stream-test")) {
            atomic_store(&stream_test_requested,true);
            if (voice_task) xTaskNotifyGive(voice_task);
        } else if (!overflow && !strcmp(line, "@voice-errors-test")) {
            printf("@mochi_voice_errors_test %s\n", voice_errors_self_test() ? "PASS" : "FAIL");
            fflush(stdout);
        } else if (!overflow && mochi_education_console(line)) {
            fflush(stdout);
        } else if (!overflow && !strcmp(line, "@controls")) {
            mochi_controls_diagnose();
        } else if (!overflow && !strcmp(line, "@gps")) {
            mochi_gps_diagnose();
        } else if (!overflow && !strcmp(line, "@gps-test")) {
            printf("@mochi_gps_test %s\n", mochi_gps_self_test() ? "PASS" : "FAIL");
            fflush(stdout);
        } else if (!overflow && !strcmp(line, "@weather")) {
            check_weather();
        } else if (!overflow && !strncmp(line, "@volume ", 8)) {
            char *end;
            long value = strtol(line + 8, &end, 10);
            if (end != line + 8 && !*end && value >= 0 && value <= 100) {
                mochi_audio_set_volume((int)value);
                mochi_controls_diagnose();
            }
        } else if (!overflow && (!strcmp(line, "@settings") || !strcmp(line, "@close"))) {
            if (esp_lv_adapter_lock(200) == ESP_OK) {
                if (!strcmp(line,"@close")) mochi_dashboard_close();
                mochi_settings_set_open(!strcmp(line, "@settings"));
                esp_lv_adapter_unlock();
            }
        }
        secure_zero(line, sizeof(line));
        used = 0;
        overflow = false;
    }
}

typedef struct {
    uint8_t *bytes;
    size_t size;
    bool overflow;
    bool stream_requested, stream_agreed, pcm_type;
    size_t played;
    int64_t first_audio_us;
    int64_t first_pcm_us;
    char emotion[24];
    char exchange_id[33];
    char navigation_id[33];
    char *caption;
    size_t caption_size;
    char education_lesson[37], requested_lesson[37];
    char education_reply[16];
    int education_step, requested_step, education_answer;
    bool education_step_valid, education_answer_valid;
    int rate, status;
} reply_t;

static void clear_caption(reply_t *reply)
{
    if(reply->caption){secure_zero(reply->caption,2801);free(reply->caption);reply->caption=NULL;}
    reply->caption_size=0;
}

static void show_education_caption(reply_t *reply)
{
    if(mochi_education_active() && reply->status==200 && reply->caption && reply->caption_size)
        mochi_education_caption(reply->caption);
}

/* Only known protocol codes are kept. Never log server bodies or spoken text. */
static const char *reply_error_code(const reply_t *reply)
{
    if (reply->status == 200 || !reply->size || reply->size > 1024) return "none";
    cJSON *json = cJSON_ParseWithLength((const char *)reply->bytes, reply->size);
    cJSON *detail = cJSON_GetObjectItemCaseSensitive(json, "detail");
    static const char *codes[] = {"no_speech_detected", "invalid_recording", "transcription_unavailable",
        "hermes_mochi_unavailable", "voice_service_unavailable", "invalid_voice_response", "mochi_busy",
        "device_auth_required"};
    const char *code = "unknown";
    if (cJSON_IsString(detail)) for (size_t i = 0; i < sizeof(codes) / sizeof(codes[0]); i++) {
        if (!strcmp(detail->valuestring, codes[i])) { code = codes[i]; break; }
    }
    cJSON_Delete(json);
    return code;
}

static const char *reply_error_notice(const reply_t *reply)
{
    const char *code = reply_error_code(reply);
    if (!strcmp(code, "no_speech_detected")) return "No te he oido. Prueba otra vez";
    if (!strcmp(code, "invalid_recording")) return "Manten pulsado mientras hablas";
    if (!strcmp(code, "transcription_unavailable")) return "No puedo reconocer la voz";
    if (!strcmp(code, "hermes_mochi_unavailable")) return "Mi modelo no esta disponible";
    if (!strcmp(code, "voice_service_unavailable")) return "No puedo generar la voz";
    if (!strcmp(code, "invalid_voice_response") || reply->status == 200) return "La voz recibida no es valida";
    if (reply->status == 401 || reply->status == 403) return "Acceso al servidor rechazado";
    if (reply->status == 429) return "El servidor esta ocupado. Espera";
    if (reply->status >= 400) return "El servidor no pudo responder";
    return "No alcanzo mi servidor";
}

static bool empty_followup(const reply_t *reply,const char *trigger)
{
    return !strcmp(trigger,"followup") && reply->status==422 &&
        !strcmp(reply_error_code(reply),"no_speech_detected");
}

static bool voice_errors_self_test(void)
{
    uint8_t silence[] = "{\"detail\":\"no_speech_detected\"}";
    reply_t reply = {.bytes = silence, .size = sizeof(silence) - 1, .status = 422};
    if (strcmp(reply_error_code(&reply), "no_speech_detected") ||
        strcmp(reply_error_notice(&reply), "No te he oido. Prueba otra vez")) return false;
    if (!empty_followup(&reply,"followup") || empty_followup(&reply,"manual") || empty_followup(&reply,"wake")) return false;
    uint8_t model[] = "{\"detail\":\"hermes_mochi_unavailable\"}";
    reply.bytes = model; reply.size = sizeof(model) - 1; reply.status = 503;
    if (empty_followup(&reply,"followup")) return false;
    if (strcmp(reply_error_notice(&reply), "Mi modelo no esta disponible")) return false;
    uint8_t unknown[] = "{\"detail\":\"untrusted server text\"}";
    reply.bytes = unknown; reply.size = sizeof(unknown) - 1;
    if (strcmp(reply_error_code(&reply), "unknown")) return false;
    reply.size = 0; reply.status = 401;
    if (strcmp(reply_error_notice(&reply), "Acceso al servidor rechazado")) return false;
    reply.status = 429;
    if (strcmp(reply_error_notice(&reply), "El servidor esta ocupado. Espera")) return false;
    reply.status = 200;
    if (strcmp(reply_error_notice(&reply), "La voz recibida no es valida")) return false;
    reply.status = 0;
    return !strcmp(reply_error_notice(&reply), "No alcanzo mi servidor");
}

static esp_err_t http_event(esp_http_client_event_t *event)
{
    reply_t *reply = event->user_data;
    if (event->event_id == HTTP_EVENT_ON_HEADER) {
        if (!strncasecmp(event->header_key,"X-Mochi-Caption-",16) &&
            strlen(event->header_key)==17 && event->header_key[16]>='1' && event->header_key[16]<='4') {
            size_t offset=(size_t)(event->header_key[16]-'1')*720, decoded=0;
            if(!reply->caption)reply->caption=heap_caps_calloc(1,2801,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
            if(reply->caption && strlen(event->header_value)<=960 && offset<2800 &&
                mbedtls_base64_decode((unsigned char *)reply->caption+offset,2800-offset,&decoded,
                    (const unsigned char *)event->header_value,strlen(event->header_value))==0) {
                if(offset+decoded>reply->caption_size)reply->caption_size=offset+decoded;
                reply->caption[reply->caption_size]=0;
            }
        }
        if (!strcasecmp(event->header_key,"X-Mochi-Lesson-Id") && strlen(event->header_value)==36)
            strlcpy(reply->education_lesson,event->header_value,sizeof(reply->education_lesson));
        if (!strcasecmp(event->header_key,"X-Mochi-Education-Reply")) {
            static const char *allowed[]={"spoken-answer","daily","tutor","retry","unavailable","support"};
            for(unsigned i=0;i<sizeof(allowed)/sizeof(allowed[0]);i++)
                if(!strcmp(event->header_value,allowed[i]))strlcpy(reply->education_reply,allowed[i],sizeof(reply->education_reply));
        }
        if (!strcasecmp(event->header_key,"X-Mochi-Lesson-Step")) {
            char *end;long n=strtol(event->header_value,&end,10);
            if(*event->header_value && !*end && n>=0 && n<5){reply->education_step=(int)n;reply->education_step_valid=true;}
        }
        if (!strcasecmp(event->header_key,"X-Mochi-Lesson-Answer")) {
            char *end;long n=strtol(event->header_value,&end,10);
            if(*event->header_value && !*end && n>=0 && n<=144){reply->education_answer=(int)n;reply->education_answer_valid=true;}
        }
        if (!strcasecmp(event->header_key, "X-Mochi-Emotion")) strlcpy(reply->emotion, event->header_value, sizeof(reply->emotion));
        if (!strcasecmp(event->header_key, "X-Mochi-Navigation")) strlcpy(reply->navigation_id,event->header_value,sizeof(reply->navigation_id));
        if (!strcasecmp(event->header_key, "X-Mochi-Sample-Rate")) reply->rate = atoi(event->header_value);
        if (!strcasecmp(event->header_key, "X-Mochi-Stream")) reply->stream_agreed = !strcmp(event->header_value,"pcm16");
        if (!strcasecmp(event->header_key, "Content-Type")) {
            static const char type[]="application/octet-stream";
            reply->pcm_type=!strncasecmp(event->header_value,type,sizeof(type)-1) &&
                (!event->header_value[sizeof(type)-1] || event->header_value[sizeof(type)-1]==';');
        }
        if (!strcasecmp(event->header_key, "X-Mochi-Request-GPS") && !strcmp(event->header_value,"1")) mochi_gps_request();
    }
    if (event->event_id == HTTP_EVENT_ON_DATA && event->data_len > 0) {
        if (reply->size + event->data_len > MAX_REPLY_BYTES) { reply->overflow = true; return ESP_FAIL; }
        if (!reply->first_pcm_us && reply->pcm_type && reply->rate==MOCHI_SAMPLE_RATE &&
            esp_http_client_get_status_code(event->client)==200) reply->first_pcm_us=esp_timer_get_time();
        memcpy(reply->bytes + reply->size, event->data, event->data_len);
        reply->size += event->data_len;
    }
    return ESP_OK;
}

/* Called only by the audio owner, after validated response headers. HTTP byte
 * boundaries need not align with samples or the codec's 256-frame blocks. */
static esp_err_t play_available(reply_t *reply, bool final)
{
    if (!reply->stream_requested || !reply->stream_agreed) return ESP_OK;
    if (reply->status!=200 || reply->rate!=MOCHI_SAMPLE_RATE || !reply->pcm_type || reply->overflow) return ESP_FAIL;
    while (reply->played<reply->size) {
        size_t available=reply->size-reply->played;
        if (available<MOCHI_AUDIO_FRAMES*2 && !final) break;
        if (available%2 && final) return ESP_FAIL;
        if (atomic_load(&cancelled) || voice_interaction_blocked() || mochi_controls_power_pending() || !server_network_ready()) return ESP_ERR_INVALID_STATE;
        size_t frames=available/2;
        if (frames>MOCHI_AUDIO_FRAMES) frames=MOCHI_AUDIO_FRAMES;
        if (!reply->played) { reply->first_audio_us=esp_timer_get_time(); ui(MOCHI_SPEAKING,0); }
        const int16_t *part=(const int16_t *)(reply->bytes+reply->played);
        level(part,frames);
        esp_err_t error=mochi_audio_write(part,frames);
        if (error!=ESP_OK) return error;
        reply->played+=frames*2;
    }
    return ESP_OK;
}

static void location_headers(esp_http_client_handle_t client)
{
    mochi_gps_status_t gps;
    mochi_gps_status(&gps);
    if (!gps.available) return;
    char value[24];
    snprintf(value, sizeof(value), "%.4f", gps.latitude);
    esp_http_client_set_header(client, "X-Mochi-Latitude", value);
    snprintf(value, sizeof(value), "%.4f", gps.longitude);
    esp_http_client_set_header(client, "X-Mochi-Longitude", value);
    snprintf(value, sizeof(value), "%d", gps.age_seconds);
    esp_http_client_set_header(client, "X-Mochi-Location-Age", value);
    esp_http_client_set_header(client, "X-Mochi-Location-Current", gps.fix ? "1" : "0");
}

static void check_weather(void)
{
    mochi_gps_status_t gps;
    mochi_gps_status(&gps);
    if (!gps.available || mochi_voice_busy() || !server_network_ready()) {
        printf("@mochi_weather ready=0 gps_available=%d busy=%d\n", gps.available, mochi_voice_busy());
        fflush(stdout);
        return;
    }
    char url[288], authorization[112], response[4096];
    snprintf(url, sizeof(url), "%s/v1/weather", config.server_url);
    esp_http_client_config_t options = {.url = url, .timeout_ms = 20000,
        .crt_bundle_attach = esp_crt_bundle_attach, .disable_auto_redirect = true};
    struct ifreq interface;
    if (!bind_server_transport(&options, &interface)) {
        printf("@mochi_weather ready=0 vpn_unavailable\n");
        fflush(stdout);
        return;
    }
    snprintf(authorization, sizeof(authorization), "Bearer %s", config.token);
    esp_http_client_handle_t client = esp_http_client_init(&options);
    int status = 0;
    bool ready = false;
    if (client) {
        esp_http_client_set_header(client, "Authorization", authorization);
        location_headers(client);
        if (esp_http_client_open(client, 0) == ESP_OK && esp_http_client_fetch_headers(client) >= 0) {
            status = esp_http_client_get_status_code(client);
            int size = esp_http_client_read_response(client, response, sizeof(response) - 1);
            if (size > 0) {
                response[size] = 0;
                cJSON *json = cJSON_Parse(response);
                ready = status == 200 && cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(json, "ready"));
                cJSON_Delete(json);
            }
        }
        esp_http_client_cleanup(client);
    }
    memset(authorization, 0, sizeof(authorization));
    printf("@mochi_weather http=%d ready=%d\n", status, ready);
    fflush(stdout);
}

static esp_err_t exchange_request(const char *route, const char *content_type,
                                  const void *data, size_t size, reply_t *reply)
{
    if (!server_network_ready()) return ESP_ERR_INVALID_STATE;
    char url[288], authorization[112];
    snprintf(url, sizeof(url), "%s%s", config.server_url, route);
    bool education=mochi_education_active();
    char education_url[256]={0},education_token[65]={0};
    if(education){
        if(!mochi_education_voice_allowed())return ESP_ERR_INVALID_STATE;
        if(strcmp(route,"/v1/turn") && strcmp(route,"/v1/education/say")) return ESP_ERR_INVALID_STATE;
        if(!mochi_education_credentials(education_url,sizeof(education_url),education_token,sizeof(education_token)))return ESP_ERR_INVALID_STATE;
        snprintf(url,sizeof(url),"%s%s",education_url,!strcmp(route,"/v1/turn")?"/v1/education/turn":route);
    }
    esp_http_client_config_t options = {.url = url, .method = HTTP_METHOD_POST,
        .timeout_ms = 180000, .crt_bundle_attach = esp_crt_bundle_attach,
        .event_handler = http_event, .user_data = reply, .buffer_size = 2048,
        .disable_auto_redirect = true};
    struct ifreq interface;
    if (!bind_server_transport(&options, &interface)) return ESP_ERR_INVALID_STATE;
    snprintf(authorization, sizeof(authorization), "Bearer %s", education?education_token:config.token);
    memset(education_token,0,sizeof(education_token));
    esp_http_client_handle_t client = esp_http_client_init(&options);
    if (!client) { secure_zero(authorization, sizeof(authorization)); return ESP_ERR_NO_MEM; }
    esp_http_client_set_header(client, "Authorization", authorization);
    esp_http_client_set_header(client, "Content-Type", content_type);
    esp_http_client_set_header(client, "X-Device-ID", device_id);
    if (reply->stream_requested) esp_http_client_set_header(client,"X-Mochi-Stream","pcm16");
    if (!strcmp(route,"/v1/turn")) {
        if (!reply->exchange_id[0]) {
            uint32_t identity[4]; esp_fill_random(identity,sizeof(identity));
            snprintf(reply->exchange_id,sizeof(reply->exchange_id),"%08lx%08lx%08lx%08lx",
                (unsigned long)identity[0],(unsigned long)identity[1],
                (unsigned long)identity[2],(unsigned long)identity[3]);
        }
        esp_http_client_set_header(client,"X-Mochi-Turn-ID",reply->exchange_id);
        if(education) {
            int step=0,a=0,b=0;char lesson[37]={0};
            if(mochi_lessons_voice_context(lesson,&step,&a,&b)) {
                char value[8];snprintf(value,sizeof(value),"%d",step);
                strlcpy(reply->requested_lesson,lesson,sizeof(reply->requested_lesson));reply->requested_step=step;
                esp_http_client_set_header(client,"X-Mochi-Lesson-Id",lesson);
                esp_http_client_set_header(client,"X-Mochi-Lesson-Step",value);
            }
        }
        mochi_options_t options; mochi_options_get(&options);
        cJSON *facts=cJSON_CreateObject();
        if (!facts) { esp_http_client_cleanup(client); secure_zero(authorization,sizeof(authorization)); return ESP_ERR_NO_MEM; }
        cJSON_AddStringToObject(facts,"name",options.name);
        cJSON_AddStringToObject(facts,"trigger",turn_trigger);
        mochi_power_status_t power; mochi_controls_power_status(&power);
        if (power.valid) {
            if (power.percent>=0) cJSON_AddNumberToObject(facts,"battery_percent",power.percent);
            cJSON_AddBoolToObject(facts,"charging",power.charging);
        }
        char *header=cJSON_PrintUnformatted(facts);
        if (header && !education) esp_http_client_set_header(client,"X-Mochi-Context",header);
        cJSON_free(header); cJSON_Delete(facts);
    }
    if(!education) location_headers(client);
    /* Keep the socket owned by this worker. Short reads let BOOT/settings
     * cancel a thinking turn without a second task touching its HTTP handle. */
    bool cancellable=education || !strcmp(route,"/v1/turn") || reply->stream_requested;
    int64_t started=esp_timer_get_time(), deadline=started+180000000;
    int64_t uploaded_us=0,headers_us=0;
    TickType_t started_tick=xTaskGetTickCount();
    esp_http_client_set_timeout_ms(client,8000);
    esp_err_t error=esp_http_client_open(client,size);
    if (error!=ESP_OK) goto exchange_done;
    for (size_t sent=0;sent<size;) {
        if (education!=mochi_education_active() || (cancellable && atomic_load(&cancelled))) { error=ESP_ERR_INVALID_STATE; goto exchange_done; }
        size_t part=size-sent; if (part>2048) part=2048;
        int written=esp_http_client_write(client,(const char *)data+sent,part);
        if (written<=0) { error=ESP_FAIL; goto exchange_done; }
        sent+=written;
    }
    uploaded_us=esp_timer_get_time();
    esp_http_client_set_timeout_ms(client,500);
    while (true) {
        if (education!=mochi_education_active() || (cancellable && (atomic_load(&cancelled) || voice_interaction_blocked() || mochi_controls_power_pending() || !server_network_ready()))) { error=ESP_ERR_INVALID_STATE; goto exchange_done; }
        if (esp_timer_get_time()>=deadline) { error=ESP_ERR_TIMEOUT; goto exchange_done; }
        int64_t headers=esp_http_client_fetch_headers(client);
        if (headers>=0) break;
        if (headers!=-ESP_ERR_HTTP_EAGAIN) { error=ESP_FAIL; goto exchange_done; }
    }
    headers_us=esp_timer_get_time();
    reply->status=esp_http_client_get_status_code(client);
    while (!esp_http_client_is_complete_data_received(client)) {
        if (education!=mochi_education_active() || (cancellable && (atomic_load(&cancelled) || voice_interaction_blocked() || mochi_controls_power_pending() || !server_network_ready()))) { error=ESP_ERR_INVALID_STATE; goto exchange_done; }
        if (esp_timer_get_time()>=deadline) { error=ESP_ERR_TIMEOUT; goto exchange_done; }
        char discard[512];
        int received=esp_http_client_read(client,discard,sizeof(discard));
        if (received==-ESP_ERR_HTTP_EAGAIN) continue;
        if (received==0 && esp_http_client_is_complete_data_received(client)) break;
        if (received<=0 || reply->overflow) { error=ESP_FAIL; goto exchange_done; }
        if ((error=play_available(reply,false))!=ESP_OK) goto exchange_done;
    }
    error=play_available(reply,true);
exchange_done:
    int status = esp_http_client_get_status_code(client);
    mochi_output_status_t output; mochi_audio_output_status(&output);
    long first_i2s_ms=reply->played && output.first_nonzero_seen?
        (long)pdTICKS_TO_MS((TickType_t)((unsigned)output.first_nonzero_tick-(unsigned)started_tick)):-1L;
    reply->status = status;
    if (error == ESP_OK && (status != 200 || reply->rate != MOCHI_SAMPLE_RATE || reply->size == 0 || reply->size % 2 || reply->overflow)) error = ESP_FAIL;
    if(error==ESP_OK && reply->navigation_id[0]) mochi_navigation_session(reply->navigation_id);
    ESP_LOGI(TAG, "Voice response: http=%d bytes=%u rate=%d overflow=%d result=%s detail=%s streamed=%d played=%u first_audio_ms=%ld first_pcm_ms=%ld first_i2s_ms=%ld upload_ms=%ld headers_ms=%ld i2s_tick_ms=%u",
             status, (unsigned)reply->size, reply->rate, reply->overflow, esp_err_to_name(error), reply_error_code(reply),
             reply->stream_agreed,(unsigned)reply->played,reply->first_audio_us?(long)((reply->first_audio_us-started)/1000):-1L,
             reply->first_pcm_us?(long)((reply->first_pcm_us-started)/1000):-1L,first_i2s_ms,
             uploaded_us?(long)((uploaded_us-started)/1000):-1L,headers_us?(long)((headers_us-started)/1000):-1L,
             (unsigned)portTICK_PERIOD_MS);
    esp_http_client_cleanup(client);
    memset(authorization, 0, sizeof(authorization));
    return error;
}

/* Download a known phrase through the actual VPN/audio route. No microphone,
 * playback, conversation memory, credential changes or network reset. */
static void check_server_audio(void)
{
    bool expected = false;
    if (!atomic_compare_exchange_strong(&busy, &expected, true)) {
        printf("@mochi_server_audio ready=0 busy=1\n");
        fflush(stdout);
        return;
    }
    reply_t reply = {.bytes = borrow_reply_buffer()};
    static const char body[] = "{\"text\":\"Hola, soy Mochi.\"}";
    esp_err_t error = reply.bytes ? exchange_request("/v1/say", "application/json", body, sizeof(body) - 1, &reply) : ESP_ERR_NO_MEM;
    printf("@mochi_server_audio ready=%d http=%d bytes=%u result=%s detail=%s\n",
           error == ESP_OK, reply.status, (unsigned)reply.size, esp_err_to_name(error), reply_error_code(&reply));
    fflush(stdout);
    return_reply_buffer(reply.bytes);
    atomic_store(&busy, false);
}

const char *mochi_runtime_device_id(void) { return device_id; }
/* Dedicated educational transport, always using the configured VPN interface.
 * Never falls back to the personal bearer token or sends GPS/context headers. */
static bool request_budget(esp_http_client_handle_t client,int64_t deadline,unsigned maximum_ms);
esp_err_t mochi_runtime_education_json(const char *base,const char *token,const char *route,const char *json,
                                      char *output,size_t capacity,int *status)
{
    if(status)*status=0;
    if(!server_network_ready() || !mochi_education_active() || !base || !token || !route || !output || capacity<2)return ESP_ERR_INVALID_STATE;
    char url[480],authorization[112];snprintf(url,sizeof(url),"%s%s",base,route);snprintf(authorization,sizeof(authorization),"Bearer %s",token);
    bool text_turn = !strcmp(route,"/v1/education/text");
    int64_t deadline=esp_timer_get_time()+(text_turn?45000000LL:5000000LL);
    esp_http_client_config_t options={.url=url,.method=HTTP_METHOD_POST,.timeout_ms=5000,.crt_bundle_attach=esp_crt_bundle_attach,.disable_auto_redirect=true,.buffer_size=1024};
    struct ifreq interface;
    if(!bind_server_transport(&options,&interface)){secure_zero(authorization,sizeof(authorization));return ESP_ERR_INVALID_STATE;}
    esp_http_client_handle_t client=esp_http_client_init(&options);if(!client){secure_zero(authorization,sizeof(authorization));return ESP_ERR_NO_MEM;}
    esp_http_client_set_header(client,"Authorization",authorization);esp_http_client_set_header(client,"Content-Type","application/json");
    size_t length=json?strlen(json):2;const char *body=json?json:"{}";esp_err_t result=esp_http_client_open(client,length);size_t used=0;
    for(size_t sent=0;result==ESP_OK&&sent<length;){
        if(text_turn && (!mochi_education_text_active() || !request_budget(client,deadline,1000))){result=ESP_ERR_INVALID_STATE;break;}
        int count=esp_http_client_write(client,body+sent,length-sent);if(count<=0)result=ESP_FAIL;else sent+=count;
    }
    if(result==ESP_OK && text_turn) {
        while (true) {
            if(!mochi_education_text_active() || !mochi_education_practice_allowed() || !request_budget(client,deadline,500)) {result=ESP_ERR_INVALID_STATE;break;}
            int64_t headers=esp_http_client_fetch_headers(client);
            if(headers>=0)break;
            if(headers!=-ESP_ERR_HTTP_EAGAIN){result=ESP_FAIL;break;}
        }
    } else if(result==ESP_OK && esp_http_client_fetch_headers(client)<0)result=ESP_FAIL;
    if(status)*status=esp_http_client_get_status_code(client);
    /* Read buffered body bytes even when fetch_headers already parsed the
     * complete short response in the same TCP packet. */
    while(result==ESP_OK){
        if(!mochi_education_active()){result=ESP_ERR_INVALID_STATE;break;}
        if(text_turn && (!mochi_education_text_active() || !mochi_education_practice_allowed() || !request_budget(client,deadline,1000))){result=ESP_ERR_INVALID_STATE;break;}
        if(used+1>=capacity){result=ESP_ERR_INVALID_SIZE;break;}
        int count=esp_http_client_read(client,output+used,capacity-used-1);
        if(count==-ESP_ERR_HTTP_EAGAIN && text_turn)continue;
        if(count<0){result=ESP_FAIL;break;}if(count==0)break;used+=count;
        if(esp_http_client_is_complete_data_received(client))break;
    }
    output[used]=0;esp_http_client_close(client);esp_http_client_cleanup(client);secure_zero(authorization,sizeof(authorization));return result;
}
static void education_speech_task(void *argument)
{
    char *event_id=argument;bool expected=false;
    if(!mochi_education_active()||!atomic_compare_exchange_strong(&busy,&expected,true)){free(event_id);atomic_store(&education_speech_pending,false);vTaskDelete(NULL);return;}
    atomic_store(&education_narrating,true);
    atomic_store(&cancelled,false);reply_t reply={.bytes=borrow_reply_buffer()};
    char body[220],question_id[37]={0};int question_step=0;
    bool question=event_id[0]=='?' && sscanf(event_id+1,"%36[^:]:%d",question_id,&question_step)==2;
    if (event_id[0] == '~' || question) {
        uint32_t id[4]; esp_fill_random(id, sizeof(id));
        if(question)snprintf(body,sizeof(body),"{\"cue\":\"question\",\"lessonId\":\"%s\",\"step\":%d,\"requestId\":\"%08lx%08lx%08lx%08lx\"}",question_id,question_step,
            (unsigned long)id[0],(unsigned long)id[1],(unsigned long)id[2],(unsigned long)id[3]);
        else snprintf(body,sizeof(body),"{\"cue\":\"%s\",\"requestId\":\"%08lx%08lx%08lx%08lx\"}", event_id+1,
            (unsigned long)id[0],(unsigned long)id[1],(unsigned long)id[2],(unsigned long)id[3]);
    } else snprintf(body,sizeof(body),"{\"eventId\":\"%s\"}",event_id);
    free(event_id);
    esp_err_t result=reply.bytes?exchange_request("/v1/education/say","application/json",body,strlen(body),&reply):ESP_ERR_NO_MEM;
    if(result==ESP_OK && question) {
        char current[37];int step=0,a=0,b=0;
        if(!mochi_lessons_voice_context(current,&step,&a,&b) || strcmp(current,question_id) || step!=question_step)
            result=ESP_ERR_INVALID_STATE;
    }
    if(result==ESP_OK)show_education_caption(&reply);
    if(result==ESP_OK)result=mochi_audio_init();
    if(result==ESP_OK&&mochi_education_active()&&!atomic_load(&cancelled)){
        ui(MOCHI_SPEAKING,0);
        for(size_t pos=0;pos<reply.size/2;pos+=MOCHI_AUDIO_FRAMES){
            if(!mochi_education_active()||!mochi_education_voice_allowed()||atomic_load(&cancelled)||voice_interaction_blocked()){result=ESP_ERR_INVALID_STATE;break;}
            size_t frames=reply.size/2-pos;if(frames>MOCHI_AUDIO_FRAMES)frames=MOCHI_AUDIO_FRAMES;
            const int16_t *part=(int16_t *)reply.bytes+pos;
            level(part,frames);
            result=mochi_audio_write(part,frames);if(result!=ESP_OK)break;
        }
        mochi_audio_idle();ui(MOCHI_HAPPY,2000);
    }
    if(question) {
        if(result==ESP_OK && !atomic_load(&cancelled))mochi_lessons_question_announced(question_id,question_step);
        else atomic_store(&education_prompt_retry_after_ms,(uint32_t)(esp_timer_get_time()/1000)+10000U);
    }
    clear_caption(&reply);
    if(reply.bytes){secure_zero(reply.bytes,reply.size);}
    return_reply_buffer(reply.bytes);atomic_store(&education_narrating,false);atomic_store(&busy,false);atomic_store(&education_speech_pending,false);vTaskDelete(NULL);
}
bool mochi_runtime_education_narrating(void) { return atomic_load(&education_narrating); }
bool mochi_runtime_education_say(const char *event_id)
{
    if(!mochi_education_active()||mochi_voice_busy()||!event_id||strlen(event_id)!=36)return false;
    char *copy=strdup(event_id);if(!copy)return false;
    if(xTaskCreate(education_speech_task,"peluqo_say",6144,copy,4,NULL)!=pdPASS){free(copy);return false;}return true;
}
bool mochi_runtime_education_cue(const char *cue)
{
    if (!cue || (strcmp(cue,"welcome") && strcmp(cue,"break") && strcmp(cue,"finished")) ||
        !mochi_education_active() || !mochi_education_voice_allowed() || mochi_voice_busy()) return false;
    char key[24]; snprintf(key,sizeof(key),"~%s",cue);
    char *copy=strdup(key); if(!copy)return false;
    if(xTaskCreate(education_speech_task,"mochi_cue",6144,copy,4,NULL)!=pdPASS){free(copy);return false;}
    return true;
}

static bool education_question_start(const char *id,int step)
{
    bool expected=false;
    if(!id || strlen(id)!=36 || step<0 || step>4 || mochi_voice_busy() ||
       !atomic_compare_exchange_strong(&education_speech_pending,&expected,true))return false;
    char key[48];snprintf(key,sizeof(key),"?%s:%d",id,step);char *copy=strdup(key);
    if(!copy || xTaskCreate(education_speech_task,"mochi_question",6144,copy,4,NULL)!=pdPASS){
        free(copy);atomic_store(&education_speech_pending,false);return false;
    }
    return true;
}
bool mochi_runtime_trusted_channel(void)
{
    uint8_t address[4];
    return server_network_ready() && (!strncmp(config.server_url,"https://",8) ||
           (http_url_ip(config.server_url,address) && overlay_address(address) && mochi_vpn_ready()));
}

esp_err_t mochi_runtime_request(const char *route,const char *json,mochi_download_sink_t sink,void *context,size_t limit,int *http_status)
{
    return mochi_runtime_request_with_timeout(route,json,sink,context,limit,http_status,180000);
}

static bool request_budget(esp_http_client_handle_t client,int64_t deadline,unsigned maximum_ms)
{
    int64_t remaining_us=deadline-esp_timer_get_time();
    if (remaining_us<=0) return false;
    unsigned remaining_ms=(unsigned)((remaining_us+999)/1000);
    return esp_http_client_set_timeout_ms(client,remaining_ms<maximum_ms?remaining_ms:maximum_ms)==ESP_OK;
}

esp_err_t mochi_runtime_request_with_timeout(const char *route,const char *json,mochi_download_sink_t sink,
                                           void *context,size_t limit,int *http_status,uint32_t timeout_ms)
{
    if (http_status) *http_status=0;
    if (!timeout_ms || timeout_ms>180000) return ESP_ERR_INVALID_ARG;
    if (!route || route[0]!='/' || strlen(route)>200 || !server_network_ready()) return ESP_ERR_INVALID_STATE;
    /* Background metadata must not masquerade as a speaking turn: otherwise
     * name-job polling wakes the display and discards wake detections. The
     * resource worker serializes its own transfers; audio owns all PCM. */
    if (mochi_voice_busy()) return ESP_ERR_INVALID_STATE;
    char url[480],authorization[112];
    snprintf(url,sizeof(url),"%s%s",config.server_url,route);
    snprintf(authorization,sizeof(authorization),"Bearer %s",config.token);
    int64_t deadline=esp_timer_get_time()+(int64_t)timeout_ms*1000;
    esp_http_client_config_t options={.url=url,.method=json?HTTP_METHOD_POST:HTTP_METHOD_GET,
        .timeout_ms=timeout_ms<5000?timeout_ms:5000,
        .crt_bundle_attach=esp_crt_bundle_attach,.disable_auto_redirect=true,.buffer_size=1024};
    struct ifreq interface;
    esp_err_t result=ESP_ERR_INVALID_STATE;
    esp_http_client_handle_t client=NULL;
    if (!bind_server_transport(&options,&interface)) goto done;
    client=esp_http_client_init(&options);
    if (!client) { result=ESP_ERR_NO_MEM; goto done; }
    esp_http_client_set_header(client,"Authorization",authorization);
    esp_http_client_set_header(client,"X-Device-ID",device_id);
    if (json) esp_http_client_set_header(client,"Content-Type","application/json");
    int length=json?strlen(json):0;
    result=esp_http_client_open(client,length);
    if (result!=ESP_OK) goto done;
    for (int sent=0;sent<length;) {
        if (!request_budget(client,deadline,1000)) { result=ESP_ERR_TIMEOUT; goto done; }
        int count=esp_http_client_write(client,json+sent,length-sent);
        if (count<=0) { result=ESP_FAIL; goto done; } sent+=count;
    }
    while (true) {
        if (!request_budget(client,deadline,500)) { result=ESP_ERR_TIMEOUT; goto done; }
        int64_t headers=esp_http_client_fetch_headers(client);
        if (headers>=0) break;
        if (headers!=-ESP_ERR_HTTP_EAGAIN) { result=ESP_FAIL; goto done; }
    }
    int status=esp_http_client_get_status_code(client);
    if (http_status) *http_status=status;
    if (status!=200 && status!=202) { result=ESP_FAIL; goto done; }
    uint8_t buffer[1024]; size_t total=0;
    while (true) {
        if (!request_budget(client,deadline,1000)) { result=ESP_ERR_TIMEOUT; goto done; }
        int count=esp_http_client_read(client,(char *)buffer,sizeof(buffer));
        if (count==-ESP_ERR_HTTP_EAGAIN) continue;
        if (count<0) { result=ESP_FAIL; goto done; }
        if (!count) break;
        if (total+(size_t)count>limit) { result=ESP_ERR_INVALID_SIZE; goto done; }
        total+=count;
        if (sink && (result=sink(buffer,count,context))!=ESP_OK) goto done;
    }
    result=esp_http_client_is_complete_data_received(client)?ESP_OK:ESP_FAIL;
done:
    if (client) esp_http_client_cleanup(client);
    secure_zero(authorization,sizeof(authorization));
    return result;
}

static void conversations(void *argument)
{
    (void)argument;
    int16_t *ring=heap_caps_calloc(MOCHI_SAMPLE_RATE,sizeof(int16_t),MALLOC_CAP_SPIRAM);
    int16_t *capture=heap_caps_malloc(MAX_RECORDING*2,MALLOC_CAP_SPIRAM);
    int16_t block[MOCHI_AUDIO_FRAMES];
    size_t ring_pos=0,ring_count=0;
    int64_t followup_until=0;
    float noise=40;
    mochi_vad_t followup_onset; mochi_vad_init(&followup_onset,noise);
    bool model_tried=false;
    bool previous_education=mochi_education_active();
    if (!ring || !capture) {
        free(ring); free(capture); voice_task=NULL; vTaskDelete(NULL); return;
    }
    while (true) {
        mochi_options_t options; mochi_options_get(&options);
        bool current_education=mochi_education_active();
        if(current_education && !mochi_voice_busy() && !atomic_load(&manual_requested) &&
           server_network_ready() && mochi_education_voice_allowed() &&
           (int32_t)((uint32_t)(esp_timer_get_time()/1000)-atomic_load(&education_prompt_retry_after_ms))>=0) {
            char lesson[37];int step=0;
            if(mochi_lessons_pending_question(lesson,&step) && education_question_start(lesson,step)) {
                vTaskDelay(pdMS_TO_TICKS(50));continue;
            }
        }
        if(current_education!=previous_education){
            secure_zero(ring,MOCHI_SAMPLE_RATE*sizeof(int16_t));
            secure_zero(capture,MAX_RECORDING*sizeof(int16_t));
            ring_count=ring_pos=0;followup_until=0;followup_active=false;
            mochi_wake_reset();previous_education=current_education;
        }
        if (atomic_exchange(&sync_test_requested,false)) {
            atomic_store(&busy,true); atomic_store(&cancelled,false);
            followup_until=0; followup_active=false;
            esp_err_t result=mochi_audio_init();
            ui(MOCHI_SPEAKING,0);
            int16_t probe_pcm[MOCHI_AUDIO_FRAMES];
            unsigned written=0;
            for (unsigned segment=0;segment<5 && result==ESP_OK;segment++) {
                for (unsigned block_number=0;block_number<32 && result==ESP_OK;block_number++) {
                    if (atomic_load(&cancelled) || voice_interaction_blocked()) { result=ESP_ERR_INVALID_STATE; break; }
                    for (unsigned i=0;i<MOCHI_AUDIO_FRAMES;i++) {
                        unsigned position=block_number*MOCHI_AUDIO_FRAMES+i;
                        probe_pcm[i]=(segment%2)?(int16_t)(3000*sinf(position*6.28318530718f*440/MOCHI_SAMPLE_RATE)):0;
                    }
                    result=mochi_audio_write(probe_pcm,MOCHI_AUDIO_FRAMES);
                    if (result==ESP_OK) written+=MOCHI_AUDIO_FRAMES;
                }
            }
            mochi_audio_idle(); ui(MOCHI_IDLE,0);
            printf("@mochi_av_test result=%s samples=%u\n",esp_err_to_name(result),written); fflush(stdout);
            ring_count=0; mochi_wake_reset(); atomic_store(&busy,false); continue;
        }
        if (atomic_exchange(&stream_test_requested,false)) {
            bool input_test=atomic_exchange(&stream_input_test_requested,false);
            atomic_store(&busy,true); atomic_store(&cancelled,false);
            followup_until=0; followup_active=false;
            reply_t probe={.stream_requested=true,.bytes=borrow_reply_buffer()};
            static const char text[]="{\"text\":\"Hola, soy Mochi. Me alegra estar contigo.\"}";
            esp_err_t result=probe.bytes?mochi_audio_init():ESP_ERR_NO_MEM;
            unsigned input_frames=0;
            if(input_test && result==ESP_OK){
                ui(MOCHI_LISTENING,0);
                /* Exercise RX DMA during drawing. Samples stay in this small
                 * overwritten block; none are stored or sent to the NAS. */
                while(input_frames<MOCHI_SAMPLE_RATE*3 && result==ESP_OK && !atomic_load(&cancelled)){
                    result=mochi_audio_read(block,MOCHI_AUDIO_FRAMES);
                    if(result==ESP_OK){input_frames+=MOCHI_AUDIO_FRAMES;level(block,MOCHI_AUDIO_FRAMES);}
                }
                ui(MOCHI_THINKING,0);
            }
            if (result==ESP_OK) result=exchange_request("/v1/say","application/json",text,sizeof(text)-1,&probe);
            mochi_audio_idle();
            printf("%s ready=%d http=%d streamed=%d bytes=%u played=%u result=%s input_frames=%u\n",
                input_test?"@mochi_mic_speaker":"@mochi_speaker_stream",
                result==ESP_OK,probe.status,probe.stream_agreed,(unsigned)probe.size,(unsigned)probe.played,esp_err_to_name(result),input_frames);
            fflush(stdout); return_reply_buffer(probe.bytes);
            ui(MOCHI_IDLE,0); ring_count=0; mochi_wake_reset(); atomic_store(&busy,false); continue;
        }
        /* The same audio owner plays navigation and conversation. A manual
         * request interrupts this short cached cue and is captured next. */
        char nav_route[112],nav_body[128];
        if(!atomic_load(&manual_requested) && !voice_interaction_blocked() &&
           mochi_navigation_audio(nav_route,sizeof(nav_route),nav_body,sizeof(nav_body))) {
            atomic_store(&busy,true); atomic_store(&navigation_speaking,true); atomic_store(&cancelled,false);
            followup_until=0; followup_active=false;
            reply_t guide={.stream_requested=true,.bytes=borrow_reply_buffer()};
            esp_err_t result=guide.bytes?mochi_audio_init():ESP_ERR_NO_MEM;
            if(result==ESP_OK && !atomic_load(&manual_requested)) result=exchange_request(nav_route,"application/json",nav_body,strlen(nav_body),&guide);
            mochi_audio_idle(); return_reply_buffer(guide.bytes); ui(MOCHI_IDLE,0);
            atomic_store(&navigation_speaking,false); atomic_store(&busy,false); ring_count=0; mochi_wake_reset();
            continue;
        }
        if (!model_tried || atomic_exchange(&reload_model,false)) {
            model_tried=true; mochi_wake_unload();
            if (options.model_id[0]) {
                char path[40]; snprintf(path,sizeof(path),"/mochi/wake%u.tflite",options.slot);
                esp_err_t error=mochi_wake_load(path,options.cutoff,options.window,options.arena_bytes);
                if (error!=ESP_OK) ESP_LOGW(TAG,"Wake model unavailable: %s",esp_err_to_name(error));
            }
        }
        if (atomic_exchange(&wake_test_requested,false)) {
            atomic_store(&busy,true); atomic_store(&cancelled,false);
            int successes=0; bool false_activation=false;
            esp_err_t error=mochi_wake_load(wake_test.path,wake_test.cutoff,wake_test.window,wake_test.arena);
            // The streaming histories require 1.5 seconds to warm. Prompting
            // first would discard a promptly spoken name on every attempt.
            // Include a negative trial so constant background triggers cannot
            // pass this local check simply by firing five times.
            for (int trial=-1;error==ESP_OK && trial<5 && !atomic_load(&cancelled) && !false_activation;trial++) {
                mochi_wake_reset();
                if (esp_lv_adapter_lock(100)==ESP_OK) {
                    mochi_show_notice("Espera: preparando microfono",0); esp_lv_adapter_unlock();
                }
                int64_t warm_until=esp_timer_get_time()+1800000;
                while (esp_timer_get_time()<warm_until && !atomic_load(&cancelled)) {
                    if (mochi_audio_read(block,MOCHI_AUDIO_FRAMES)!=ESP_OK) { error=ESP_FAIL; break; }
                    mochi_wake_feed(block,MOCHI_AUDIO_FRAMES);
                }
                if (error!=ESP_OK || atomic_load(&cancelled)) break;
                if (esp_lv_adapter_lock(100)==ESP_OK) {
                    char message[64]; snprintf(message,sizeof(message),"Di el nuevo nombre: %d de 5",trial+1);
                    mochi_show_notice(trial<0?"Habla 6 s sin decir el nombre":message,0); esp_lv_adapter_unlock();
                }
                int64_t end=esp_timer_get_time()+(trial<0?6000000:4000000);
                bool detected=false;
                while (esp_timer_get_time()<end && !atomic_load(&cancelled)) {
                    if (mochi_audio_read(block,MOCHI_AUDIO_FRAMES)!=ESP_OK) { error=ESP_FAIL; break; }
                    if (!detected && mochi_wake_feed(block,MOCHI_AUDIO_FRAMES)) {
                        if (trial<0) { false_activation=true; break; }
                        successes++; detected=true;
                    }
                }
            }
            atomic_store(&wake_test_result,error==ESP_OK && !false_activation && successes>=4 && !atomic_load(&cancelled)?1:-1);
            atomic_store(&reload_model,true); atomic_store(&busy,false); ring_count=0; continue;
        }
        bool manual=atomic_exchange(&manual_requested,false);
        bool automatic=false;
        if (!manual) {
            if(mochi_education_active()){followup_until=0;followup_active=false;ring_count=0;mochi_wake_reset();ulTaskNotifyTake(pdTRUE,pdMS_TO_TICKS(50));continue;}
            if (!options.microphone || voice_interaction_blocked() || mochi_controls_power_pending() || !server_network_ready()) {
                followup_until=0; followup_active=false; mochi_wake_reset(); ring_count=0;
                ulTaskNotifyTake(pdTRUE,pdMS_TO_TICKS(50)); continue;
            }
            if (atomic_exchange(&cancelled,false)) { followup_until=0; followup_active=false; ring_count=0; mochi_wake_reset(); }
            if (followup_until && esp_timer_get_time()>=followup_until) { followup_until=0; followup_active=false; ui(MOCHI_IDLE,0); }
            if (!followup_until && (!options.handsfree || !mochi_wake_ready())) {
                ulTaskNotifyTake(pdTRUE,pdMS_TO_TICKS(50)); continue;
            }
            if (mochi_audio_read(block,MOCHI_AUDIO_FRAMES)!=ESP_OK) { vTaskDelay(pdMS_TO_TICKS(100)); continue; }
            for (size_t i=0;i<MOCHI_AUDIO_FRAMES;i++) { ring[ring_pos]=block[i]; ring_pos=(ring_pos+1)%MOCHI_SAMPLE_RATE; if (ring_count<MOCHI_SAMPLE_RATE) ring_count++; }
            bool voiced=mochi_vad_voiced(block,MOCHI_AUDIO_FRAMES,noise);
            if (!voiced) {
                double energy=0; for (size_t i=0;i<MOCHI_AUDIO_FRAMES;i++) energy+=(double)block[i]*block[i];
                noise=.98f*noise+.02f*fminf(300,sqrtf(energy/MOCHI_AUDIO_FRAMES));
            }
            if (followup_until) {
                followup_onset.noise=noise;
                mochi_vad_step(&followup_onset,block,MOCHI_AUDIO_FRAMES,8000);
                automatic=followup_onset.heard;
            } else automatic=mochi_wake_feed(block,MOCHI_AUDIO_FRAMES);
            if (!automatic) continue;
            turn_trigger=followup_until?"followup":"wake";
        } else turn_trigger="manual";
        bool expected=false;
        if (!atomic_compare_exchange_strong(&busy,&expected,true)) continue;
        int64_t resume_followup_until=!strcmp(turn_trigger,"followup")?followup_until:0;
        followup_until=0; followup_active=false;
        atomic_store(&cancelled,false);
        reply_t reply = {.stream_requested=true};
        const char *stage = "network", *notice = NULL;
        esp_err_t error = ESP_ERR_INVALID_STATE;
        if (voice_interaction_blocked()) goto finished;
        if (config.magic != CONFIG_MAGIC) {
            if (esp_lv_adapter_lock(200) == ESP_OK) {
                mochi_show_notice("Voz aun sin configurar", 3500);
                esp_lv_adapter_unlock();
            }
            goto finished;
        }
        if (!server_network_ready()) {
            notice = !(xEventGroupGetBits(network) & BIT0) ? "Conectando al Wi-Fi. Espera" :
                !mochi_vpn_ready() ? "Conectando a la VPN. Espera" : "Servidor sin configurar";
            goto failed;
        }
        stage = "audio_init"; notice = "No puedo iniciar el audio";
        if ((error = mochi_audio_init()) != ESP_OK) goto failed;
        stage = "memory"; notice = "Falta memoria para hablar";
        reply.bytes = borrow_reply_buffer();
        if (!capture || !reply.bytes) { error = ESP_ERR_NO_MEM; goto failed; }
        if (!current_education) ui(MOCHI_LISTENING, 0);
        size_t samples = 0;
        mochi_vad_t vad; mochi_vad_init(&vad,noise);
        stage = "microphone"; notice = "No puedo usar el microfono";
        if (automatic) {
            size_t start=(ring_pos+MOCHI_SAMPLE_RATE-ring_count)%MOCHI_SAMPLE_RATE;
            for (size_t i=0;i<ring_count;i++) capture[samples++]=ring[(start+i)%MOCHI_SAMPLE_RATE];
            if (!strcmp(turn_trigger,"followup")) {
                /* A measured 100 ms onset starts capture. Waiting silence
                 * does not consume the new question's audio budget. */
                vad=followup_onset; vad.elapsed=(uint32_t)ring_count;
            }
        } else for (int i=0;i<8;i++) if ((error=mochi_audio_read(block,MOCHI_AUDIO_FRAMES))!=ESP_OK) goto failed;
        if (current_education && atomic_load(&recording)) {
            mochi_education_notice("", 0);
            ui(MOCHI_LISTENING, 0);
        }
        ring_count=0;
        while ((automatic || atomic_load(&recording)) && !atomic_load(&cancelled) && !voice_interaction_blocked() &&
               samples + MOCHI_AUDIO_FRAMES <= MAX_RECORDING) {
            if ((error = mochi_audio_read(capture + samples, MOCHI_AUDIO_FRAMES)) != ESP_OK) goto failed;
            if (samples % (MOCHI_AUDIO_FRAMES * 4) == 0) level(capture + samples, MOCHI_AUDIO_FRAMES);
            samples += MOCHI_AUDIO_FRAMES;
            if (automatic && mochi_vad_step(&vad,capture+samples-MOCHI_AUDIO_FRAMES,MOCHI_AUDIO_FRAMES,4000)!=MOCHI_VAD_MORE) break;
        }
        atomic_store(&recording, false);
        if(current_education) {
            int peak=0;double sum=0;
            for(size_t i=0;i<samples;i++){int value=capture[i];if(abs(value)>peak)peak=abs(value);sum+=(double)value*value;}
            ESP_LOGI(TAG,"Voice capture: samples=%u peak=%d rms=%u cancelled=%d blocked=%d",
                (unsigned)samples,peak,samples?(unsigned)sqrt(sum/samples):0,
                atomic_load(&cancelled),voice_interaction_blocked());
        }
        if (atomic_load(&cancelled) || voice_interaction_blocked() || (automatic && !vad.heard)) { ui(MOCHI_IDLE,0); goto finished; }
        if (samples < MOCHI_SAMPLE_RATE / 5) {
            if (current_education) mochi_education_notice("Manten pulsado mientras hablas", 4000);
            ui(MOCHI_IDLE, 0);
            goto finished;
        }
        ui(MOCHI_THINKING, 0);
        if (!strncmp(config.server_url, "https://", 8)) {
            stage = "clock"; notice = "Sincronizando la hora. Espera";
            for (int i = 0; i < 100 && time(NULL) < 1700000000; i++) vTaskDelay(pdMS_TO_TICKS(100));
            if (time(NULL) < 1700000000) { error = ESP_ERR_TIMEOUT; goto failed; }
        }
        mochi_navigation_hide();
        stage = "server"; notice = NULL;
        if ((error = exchange_request("/v1/turn", "application/octet-stream", capture, samples * 2, &reply)) != ESP_OK) goto failed;
        show_education_caption(&reply);
        if(current_education)ESP_LOGI(TAG,"Education reply: kind=%s context=%d answer=%d step=%d",
            reply.education_reply[0]?reply.education_reply:"none",reply.requested_lesson[0]!=0,
            reply.education_answer_valid,reply.education_step_valid?reply.education_step:-1);
        if (atomic_load(&cancelled) || voice_interaction_blocked()) goto finished;
        if (!reply.stream_agreed) ui(MOCHI_SPEAKING, 0);
        stage = "speaker"; notice = "No puedo reproducir la voz";
        for (size_t position = reply.played / 2; position < reply.size / 2; position += MOCHI_AUDIO_FRAMES) {
            if (atomic_load(&cancelled) || voice_interaction_blocked()) break;
            size_t frames = reply.size / 2 - position;
            if (frames > MOCHI_AUDIO_FRAMES) frames = MOCHI_AUDIO_FRAMES;
            const int16_t *part = (int16_t *)reply.bytes + position;
            level(part, frames);
            if ((error = mochi_audio_write(part, frames)) != ESP_OK) goto failed;
        }
        /* Drain the last DMA audio before changing away from the talking face. */
        mochi_audio_idle();
        if(current_education) {
            bool matched=reply.education_answer_valid && reply.education_step_valid &&
                reply.requested_lesson[0] && !strcmp(reply.requested_lesson,reply.education_lesson) && reply.requested_step==reply.education_step;
            bool applied=!atomic_load(&cancelled) && matched &&
                mochi_lessons_spoken_answer(reply.education_lesson,reply.education_step,reply.education_answer);
            ESP_LOGI(TAG,"Education answer: matched=%d applied=%d cancelled=%d",matched,applied,atomic_load(&cancelled));
        }
        ui(mochi_state_from_name(reply.emotion), 3500);
        if (!mochi_education_active() && !atomic_load(&cancelled) && !voice_interaction_blocked() && options.microphone) {
            mochi_audio_idle();
            int64_t until=esp_timer_get_time()+400000;
            float ambient[16]; size_t ambient_count=0,ambient_pos=0;
            while (esp_timer_get_time()<until) {
                if (mochi_audio_read(block,MOCHI_AUDIO_FRAMES)!=ESP_OK) break;
                double energy=0; for (size_t i=0;i<MOCHI_AUDIO_FRAMES;i++) energy+=(double)block[i]*block[i];
                ambient[ambient_pos]=sqrtf(energy/MOCHI_AUDIO_FRAMES);
                ambient_pos=(ambient_pos+1)%16; if (ambient_count<16) ambient_count++;
            }
            if (ambient_count) {
                for (size_t i=1;i<ambient_count;i++) {
                    float value=ambient[i]; size_t j=i;
                    while (j && ambient[j-1]>value) { ambient[j]=ambient[j-1]; j--; }
                    ambient[j]=value;
                }
                /* Low quartile ignores residual echo and brief transients. */
                noise=fmaxf(40,fminf(1500,ambient[ambient_count/4]));
            }
            mochi_vad_init(&followup_onset,noise);
            followup_until=esp_timer_get_time()+8000000; followup_active=true;
            ui(MOCHI_LISTENING,0);
        }
        goto finished;
failed:
        if (empty_followup(&reply,turn_trigger) && resume_followup_until>esp_timer_get_time() &&
            !atomic_load(&cancelled) && !voice_interaction_blocked() && server_network_ready()) {
            /* A noise onset rejected by ASR spends time from this window;
             * it neither closes it early nor opens a new eight-second one. */
            mochi_vad_init(&followup_onset,noise);
            followup_until=resume_followup_until; followup_active=true;
            ui(MOCHI_LISTENING,0);
            goto finished;
        }
        ESP_LOGW(TAG, "Voice failed: stage=%s result=%s http=%d detail=%s", stage, esp_err_to_name(error), reply.status, reply_error_code(&reply));
        if (!atomic_load(&cancelled) && esp_lv_adapter_lock(200) == ESP_OK) {
            mochi_show_notice(notice ? notice : reply_error_notice(&reply), 5000);
            esp_lv_adapter_unlock();
        }
finished:
        mochi_audio_idle();
        clear_caption(&reply);
        return_reply_buffer(reply.bytes);
        ring_count=0; mochi_wake_reset();
        atomic_store(&recording, false);
        atomic_store(&busy, false);
    }
}

void mochi_runtime_start(void)
{
    network = xEventGroupCreate();
    if (!network) return;
    nvs_ready = nvs_flash_init() == ESP_OK;
    nvs_handle_t handle;
    size_t length = sizeof(config);
    if (nvs_ready && nvs_open("mochi", NVS_READONLY, &handle) == ESP_OK) {
        if (nvs_get_blob(handle, "config", &config, &length) != ESP_OK || length != sizeof(config)) memset(&config, 0, sizeof(config));
        nvs_close(handle);
    }
    if (config.magic == CONFIG_MAGIC &&
        (!memchr(config.ssid, 0, sizeof(config.ssid)) || !memchr(config.password, 0, sizeof(config.password)) ||
         !memchr(config.server_url, 0, sizeof(config.server_url)) || !memchr(config.token, 0, sizeof(config.token))))
        secure_zero(&config, sizeof(config));
    /* Older 0.6 builds saved an alternative only after an explicit successful
     * selection, so prefer that network when the new preference key is absent. */
    uint8_t preferred_wifi = 1;
    length = sizeof(alternate_wifi);
    if (nvs_ready && nvs_open("mochi_wifi", NVS_READONLY, &handle) == ESP_OK) {
        if (nvs_get_blob(handle, "alt", &alternate_wifi, &length) != ESP_OK || length != sizeof(alternate_wifi))
            secure_zero(&alternate_wifi, sizeof(alternate_wifi));
        nvs_get_u8(handle, "preferred", &preferred_wifi);
        nvs_close(handle);
    }
    if (alternate_wifi.magic != WIFI_ALT_MAGIC ||
        !memchr(alternate_wifi.ssid, 0, sizeof(alternate_wifi.ssid)) ||
        !memchr(alternate_wifi.password, 0, sizeof(alternate_wifi.password)) ||
        !valid_wifi(alternate_wifi.ssid, alternate_wifi.password))
        secure_zero(&alternate_wifi, sizeof(alternate_wifi));
    atomic_store(&wifi_has_alternate, alternate_wifi.magic == WIFI_ALT_MAGIC);
    bool start_alternate = alternate_wifi.magic == WIFI_ALT_MAGIC && preferred_wifi != 0;
    atomic_store(&wifi_using_alternate, start_alternate);
    uint8_t mac[6];
    esp_read_mac(mac, ESP_MAC_WIFI_STA);
    snprintf(device_id, sizeof(device_id), "mochi-%02x%02x%02x%02x%02x%02x", mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
    mochi_vpn_prepare();
    if (xTaskCreatePinnedToCore(conversations, "mochi_voice", 8192, NULL, 4, &voice_task, 0) != pdPASS) voice_task = NULL;
    xTaskCreate(console, "mochi_setup", 12288, NULL, 2, NULL);
    if (config.magic != CONFIG_MAGIC) { ESP_LOGI(TAG, "Device setup required over USB"); return; }
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();
    wifi_init_config_t wifi = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&wifi));
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, wifi_event, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, wifi_event, NULL));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(set_wifi_credentials(start_alternate));
    if (xTaskCreatePinnedToCore(wifi_worker_task, "mochi_wifi", 6144, NULL, 2, &wifi_worker, 0) != pdPASS) {
        wifi_worker = NULL;
        wifi_publish_phase(MOCHI_WIFI_FAILED, MOCHI_WIFI_ERROR_UNAVAILABLE);
        ESP_LOGE(TAG, "Wi-Fi worker unavailable");
        return;
    }
    ESP_ERROR_CHECK(esp_wifi_start());
    mochi_navigation_start();
    atomic_store(&wifi_control_ready, true);
    esp_sntp_setoperatingmode(SNTP_OPMODE_POLL);
    esp_sntp_setservername(0, "pool.ntp.org");
    esp_sntp_init();
}
