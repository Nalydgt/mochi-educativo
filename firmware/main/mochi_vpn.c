/* Private, application-only Tailscale node. No subnet routes or public listener. */
#include "mochi_vpn.h"
#include "microlink.h"
#include "cJSON.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "lwip/inet.h"
#include "lwip/netif.h"
#include "lwip/sockets.h"
#include "nvs.h"
#include "psa/crypto.h"
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define VPN_MAGIC UINT32_C(0x4d565001)
typedef struct { uint32_t magic; char key[128], peer[16]; } vpn_config_t;
static const char *TAG = "mochi_vpn";
static atomic_bool prepared, worker_created, connected;
static atomic_uint requests;
static _Atomic(TaskHandle_t) manager_task;
static portMUX_TYPE status_lock = portMUX_INITIALIZER_UNLOCKED;
static struct {
    int phase, state, error, peers;
    uint32_t ip;
    uint16_t derp, priority_derp;
    bool direct, persistent, crypto, relay;
} snapshot;

static void clear_secret(void *bytes, size_t size)
{
    volatile unsigned char *p = bytes;
    while (size--) *p++ = 0;
}

static bool valid_config(const vpn_config_t *config)
{
    if (config->magic != VPN_MAGIC || !memchr(config->key, 0, sizeof(config->key)) ||
        !memchr(config->peer, 0, sizeof(config->peer))) return false;
    size_t length = strlen(config->key);
    if (length < 32 || length >= sizeof(config->key) || strncmp(config->key, "tskey-auth-", 11)) return false;
    for (const char *c = config->key; *c; c++)
        if (!((*c >= 'A' && *c <= 'Z') || (*c >= 'a' && *c <= 'z') ||
              (*c >= '0' && *c <= '9') || *c == '-' || *c == '_')) return false;
    struct in_addr address;
    if (inet_pton(AF_INET, config->peer, &address) != 1) return false;
    return (ntohl(address.s_addr) & UINT32_C(0xffc00000)) == UINT32_C(0x64400000);
}

static bool load_config(vpn_config_t *config)
{
    nvs_handle_t handle;
    size_t size = sizeof(*config);
    if (nvs_open("mochi_vpn", NVS_READONLY, &handle) != ESP_OK) return false;
    esp_err_t error = nvs_get_blob(handle, "config", config, &size);
    nvs_close(handle);
    return error == ESP_OK && size == sizeof(*config) && valid_config(config);
}

bool mochi_vpn_configured(void)
{
    vpn_config_t config = {0};
    bool valid = load_config(&config);
    clear_secret(&config, sizeof(config));
    return valid;
}

bool mochi_vpn_configure(const char *auth_key, const char *priority_peer_ip)
{
    if (!auth_key || !priority_peer_ip || strlen(auth_key) >= 128 || strlen(priority_peer_ip) >= 16) return false;
    vpn_config_t config = {.magic = VPN_MAGIC};
    memcpy(config.key, auth_key, strlen(auth_key) + 1);
    memcpy(config.peer, priority_peer_ip, strlen(priority_peer_ip) + 1);
    if (!valid_config(&config)) { clear_secret(&config, sizeof(config)); return false; }
    nvs_handle_t handle;
    esp_err_t result = nvs_open("mochi_vpn", NVS_READWRITE, &handle);
    if (result == ESP_OK) {
        result = nvs_set_blob(handle, "config", &config, sizeof(config));
        if (result == ESP_OK) result = nvs_commit(handle);
        nvs_close(handle);
    }
    clear_secret(&config, sizeof(config));
    return result == ESP_OK;
}

static void *json_allocate(size_t size)
{
    void *bytes = heap_caps_malloc(size, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    return bytes ? bytes : heap_caps_malloc(size, MALLOC_CAP_8BIT);
}

void mochi_vpn_prepare(void)
{
    /* cJSON hooks are global: set them before concurrent parsers exist. */
    bool expected = false;
    if (!atomic_compare_exchange_strong(&prepared, &expected, true)) return;
    cJSON_Hooks hooks = {.malloc_fn = json_allocate, .free_fn = free};
    cJSON_InitHooks(&hooks);
}

static uint32_t wifi_ip(void)
{
    esp_netif_t *sta = esp_netif_get_handle_from_ifkey("WIFI_STA_DEF");
    esp_netif_ip_info_t info = {0};
    return sta && esp_netif_is_netif_up(sta) && esp_netif_get_ip_info(sta, &info) == ESP_OK ? info.ip.addr : 0;
}

static void phase(int value, esp_err_t error)
{
    portENTER_CRITICAL(&status_lock);
    snapshot.phase = value;
    snapshot.error = error;
    portEXIT_CRITICAL(&status_lock);
}

static void manager(void *argument)
{
    (void)argument;
    /* These buffers remain alive for the session; MicroLink stores pointers. */
    vpn_config_t config = {0};
    while (!load_config(&config)) {
        clear_secret(&config, sizeof(config));
        phase(0, ESP_OK);
        ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(1000));
    }
    phase(1, ESP_OK);
    while (!wifi_ip() || time(NULL) < 1700000000) vTaskDelay(pdMS_TO_TICKS(1000));
    if (!mochi_vpn_self_test()) { phase(4, ESP_FAIL); goto stopped; }
    ESP_LOGI(TAG, "Starting private VPN node after certificate clock and crypto checks");
    /* Keep protocol logs quiet; the USB snapshot below never prints secrets. */
    const char *tags[] = {"microlink", "ml_coord", "ml_derp", "ml_net_io", "ml_wg_mgr",
        "ml_noise", "ml_h2", "ml_stun", "ml_netcheck", "ml_peer_nvs", "wireguardif"};
    for (unsigned i = 0; i < sizeof(tags) / sizeof(tags[0]); i++) esp_log_level_set(tags[i], ESP_LOG_WARN);
    microlink_config_t options = {
        .auth_key = config.key, .device_name = "mochi-device", .enable_derp = true,
        .ctrl_host = "https://controlplane.tailscale.com",
        .enable_stun = true, .enable_disco = true, .max_peers = 2,
        .priority_peer_ip = microlink_parse_ip(config.peer), .derp_tls_verify = true,
        .follow_priority_derp = true,
        .disco_heartbeat_ms = 10000, .stun_interval_ms = 30000,
    };
    microlink_t *node = microlink_init(&options);
    if (!node) { phase(4, ESP_ERR_NO_MEM); goto stopped; }
    unsigned observed = atomic_load(&requests);
    esp_err_t error = microlink_start(node);
    if (error != ESP_OK) {
        phase(4, error);
        /* Keep ownership: never free memory that a partially stopped task might use. */
        goto stopped;
    }
    phase(2, ESP_OK);
    while (true) {
        ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(1000));
        unsigned requested = atomic_load(&requests);
        if (requested != observed) {
            observed = requested;
            uint32_t current = wifi_ip();
            if (current) {
                atomic_store(&connected, false);
                error = microlink_rebind(node);
                phase(2, error);
            }
        }
        microlink_diag_t diagnostic = {0};
        if (microlink_get_diag(node, &diagnostic) == ESP_OK) {
            bool ready = diagnostic.connected && diagnostic.derp_connected && diagnostic.vpn_ip && wifi_ip();
            bool direct = false;
            for (int i = 0; i < diagnostic.peer_count; i++) {
                microlink_peer_info_t peer;
                if (microlink_get_peer_info(node, i, &peer) == ESP_OK &&
                    peer.vpn_ip == options.priority_peer_ip) direct = peer.direct_path;
            }
            portENTER_CRITICAL(&status_lock);
            snapshot.state = diagnostic.state;
            snapshot.ip = diagnostic.vpn_ip;
            snapshot.peers = diagnostic.peer_count;
            snapshot.direct = direct;
            snapshot.persistent = diagnostic.identity_persistent;
            snapshot.derp = diagnostic.derp_home_region;
            snapshot.priority_derp = diagnostic.priority_derp_region;
            snapshot.relay = diagnostic.derp_connected;
            portEXIT_CRITICAL(&status_lock);
            atomic_store(&connected, ready);
        }
        /* A rotated key needs a clean boot so no task retains the old key. */
        if (microlink_restart_requested(node)) {
            atomic_store(&connected, false);
            phase(5, ESP_ERR_INVALID_STATE);
        }
    }
stopped:
    /* Failure remains visible; a reboot retries without spawning duplicate tasks. */
    atomic_store(&connected, false);
    clear_secret(&config, sizeof(config));
    for (;;) ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
}

void mochi_vpn_start(void)
{
    if (!atomic_load(&prepared)) { phase(4, ESP_ERR_INVALID_STATE); return; }
    atomic_fetch_add(&requests, 1);
    bool expected = false;
    if (atomic_compare_exchange_strong(&worker_created, &expected, true)) {
        TaskHandle_t task;
        if (xTaskCreatePinnedToCore(manager, "mochi_vpn", 4096, NULL, 1, &task, 0) != pdPASS) {
            atomic_store(&worker_created, false);
            phase(4, ESP_ERR_NO_MEM);
            return;
        }
        atomic_store(&manager_task, task);
    } else {
        TaskHandle_t task = atomic_load(&manager_task);
        if (task) xTaskNotifyGive(task);
    }
}

bool mochi_vpn_ready(void) { return atomic_load(&connected); }
const char *mochi_vpn_status_text(void)
{
    if(!mochi_vpn_configured())return "VPN: sin configurar";
    if(mochi_vpn_ready())return "VPN: lista";
    portENTER_CRITICAL(&status_lock);
    int stage=snapshot.phase,error=snapshot.error;
    portEXIT_CRITICAL(&status_lock);
    if(stage==4)return error==ESP_ERR_NO_MEM?"VPN: memoria insuficiente":"VPN: error al iniciar";
    if(stage==5)return "VPN: reinicia Mochi";
    return "VPN: conectando";
}

struct bind_request { uint32_t ip; struct ifreq *interface; bool found; };
static esp_err_t bind_on_tcpip(void *argument)
{
    struct bind_request *request = argument;
    for (struct netif *item = netif_list; item; item = item->next) {
        /* A passive WireGuard peer has no link until its first handshake.
         * Permit the bound SYN to trigger that handshake; the explicit WG
         * interface index still forbids a fallback to the Wi-Fi interface. */
        if (item->name[0] != 'w' || item->name[1] != 'g' ||
            !netif_is_up(item) ||
            ntohl(netif_ip4_addr(item)->addr) != request->ip) continue;
        uint8_t index = netif_get_index(item);
        if (!index || netif_get_by_index(index) != item) continue;
        request->found = netif_index_to_name(index, request->interface->ifr_name) != NULL;
        if (request->found) break;
    }
    return ESP_OK;
}

bool mochi_vpn_bind_interface(const char *peer_ip, struct ifreq *out)
{
    if (!peer_ip || !out || !mochi_vpn_ready()) return false;
    memset(out, 0, sizeof(*out));
    vpn_config_t config = {0};
    bool allowed = load_config(&config) && !strcmp(peer_ip, config.peer);
    clear_secret(&config, sizeof(config));
    if (!allowed) return false;
    portENTER_CRITICAL(&status_lock);
    uint32_t ip = snapshot.ip;
    portEXIT_CRITICAL(&status_lock);
    struct bind_request request = {.ip = ip, .interface = out};
    return esp_netif_tcpip_exec(bind_on_tcpip, &request) == ESP_OK && request.found &&
        mochi_vpn_ready() && out->ifr_name[0];
}

bool mochi_vpn_self_test(void)
{
    bool passed = psa_crypto_init() == PSA_SUCCESS && microlink_crypto_self_test();
    portENTER_CRITICAL(&status_lock);
    snapshot.crypto = passed;
    portEXIT_CRITICAL(&status_lock);
    return passed;
}

void mochi_vpn_diagnose(void)
{
    portENTER_CRITICAL(&status_lock);
    int current_phase = snapshot.phase, state = snapshot.state, error = snapshot.error, peers = snapshot.peers;
    uint32_t ip = snapshot.ip;
    bool direct = snapshot.direct, persistent = snapshot.persistent, crypto = snapshot.crypto;
    bool relay = snapshot.relay;
    unsigned derp = snapshot.derp, priority_derp = snapshot.priority_derp;
    portEXIT_CRITICAL(&status_lock);
    printf("@mochi_vpn configured=%d worker=%d phase=%d state=%d ready=%d peers=%d direct=%d persistent=%d crypto=%d ip=%lu.%lu.%lu.%lu error=%d internal_free=%u psram_free=%u derp=%u priority_derp=%u relay=%d internal_largest=%u\n",
        mochi_vpn_configured(), atomic_load(&worker_created), current_phase, state, mochi_vpn_ready(), peers,
        direct, persistent, crypto, (unsigned long)(ip >> 24), (unsigned long)((ip >> 16) & 255),
        (unsigned long)((ip >> 8) & 255), (unsigned long)(ip & 255), error,
        (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT),
        (unsigned)heap_caps_get_free_size(MALLOC_CAP_SPIRAM), derp, priority_derp, relay,
        (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT));
    fflush(stdout);
}
