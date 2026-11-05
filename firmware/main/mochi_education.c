/* Educational session overlay. Always preserves the original Mochi renderer. */
#include "mochi_education.h"
#include "cJSON.h"
#include "esp_heap_caps.h"
#include "esp_random.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "mochi_display.h"
#include "mochi_fonts.h"
#include "mochi_options.h"
#include "mochi_audio.h"
#include "mochi_runtime.h"
#include "mochi_lessons.h"
#include "mochi_lesson_scene.h"
#include "mochi_education_policy.h"
#include "nvs.h"
#include "psa/crypto.h"
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

extern esp_err_t mochi_runtime_education_json(const char *, const char *, const char *,
                                              const char *, char *, size_t, int *);
extern bool mochi_runtime_education_say(const char *event_id);
typedef struct {
    char url[256], provision[65], token[65], salt[33], pin_hash[65];
    bool enabled;
} settings_t;
typedef struct {
    char name[64], status[160], code[9], pending[80], session[40];
    mochi_state_t mood;
} view_t;
static settings_t settings;
static view_t view = {.name = "Peluqo", .status = "Preparando la aventura"};
static SemaphoreHandle_t mutex;
static atomic_bool active;
static atomic_bool renewing;
static atomic_bool reaction_pending;
static atomic_bool online;
static lv_obj_t *screen, *name_label, *status_label, *code_label, *panel, *pin, *keyboard,
    *pin_hint;
static lv_obj_t *conversation_panel, *conversation_scroll, *conversation_label;
static char *conversation_text;
static atomic_bool conversation_open;
static unsigned conversation_revision, conversation_rendered;
static atomic_bool options_open;
enum { QUICK_CLOSED, QUICK_HOME, QUICK_SOUND };
static atomic_int quick_page;
static lv_obj_t *quick_panel, *quick_home, *quick_sound, *sound_value, *sound_mute, *sound_hint;
static lv_obj_t *reminder_toast, *reminder_label;
static int unmuted_volume = 45;
static int64_t reminder_left, reminder_at;
static void quick_show(int page);
static void create_quick_menu(void);
static char notice_text[160];
static int64_t notice_until;
void mochi_education_notice(const char *text, int duration_ms) {
    if (!mutex || !mochi_education_active())
        return;
    xSemaphoreTake(mutex, portMAX_DELAY);
    snprintf(notice_text, sizeof(notice_text), "%s", text);
    notice_until = duration_ms > 0 ? esp_timer_get_time() + (int64_t)duration_ms * 1000 : 0;
    xSemaphoreGive(mutex);
}
void mochi_education_caption(const char *text) {
    if (!text || !mutex || !mochi_education_active() || !mochi_education_policy_captions())
        return;
    if (mochi_lessons_interacting()) {
        mochi_lessons_voice_caption(text);
        return;
    }
    xSemaphoreTake(mutex, portMAX_DELAY);
    if (conversation_text) {
        snprintf(conversation_text, 2801, "%s", text);
        conversation_revision++;
        atomic_store(&conversation_open, conversation_text[0] != 0);
    }
    xSemaphoreGive(mutex);
}
static lv_indev_t *diagnostic_pointer;
static lv_point_t diagnostic_point;
static bool diagnostic_pressed;
static void read_diagnostic_pointer(lv_indev_t *input, lv_indev_data_t *data) {
    (void)input;
    data->point = diagnostic_point;
    data->state = diagnostic_pressed ? LV_INDEV_STATE_PRESSED : LV_INDEV_STATE_RELEASED;
}
bool mochi_education_pointer(int x, int y, bool pressed) {
    if (x == -1 && y == -1 && !pressed) {
        if (!diagnostic_pointer)
            return false;
        lv_indev_delete(diagnostic_pointer);
        diagnostic_pointer = NULL;
        diagnostic_pressed = false;
        return true;
    }
    if (!mochi_education_active() || !screen || x < 0 || y < 0 || x >= 466 || y >= 466)
        return false;
    if (!diagnostic_pointer) {
        diagnostic_pointer = lv_indev_create();
        if (!diagnostic_pointer)
            return false;
        lv_indev_set_type(diagnostic_pointer, LV_INDEV_TYPE_POINTER);
        lv_indev_set_display(diagnostic_pointer, lv_obj_get_display(screen));
        lv_indev_set_read_cb(diagnostic_pointer, read_diagnostic_pointer);
    }
    diagnostic_point = (lv_point_t){x, y};
    diagnostic_pressed = pressed;
    lv_timer_ready(lv_indev_get_read_timer(diagnostic_pointer));
    return true;
}
static void save(void) {
    nvs_handle_t n;
    if (nvs_open("peluqo", NVS_READWRITE, &n) == ESP_OK) {
        nvs_set_blob(n, "settings", &settings, sizeof(settings));
        nvs_commit(n);
        nvs_close(n);
    }
}
static void digest(const char *value, char output[65]) {
    unsigned char bytes[32] = {0};
    size_t length = 0;
    psa_crypto_init();
    if (psa_hash_compute(PSA_ALG_SHA_256, (const unsigned char *)value, strlen(value), bytes,
                         sizeof(bytes), &length) != PSA_SUCCESS ||
        length != 32) {
        memset(output, 0, 65);
        return;
    }
    for (int i = 0; i < 32; i++)
        snprintf(output + i * 2, 3, "%02x", bytes[i]);
    memset(bytes, 0, sizeof(bytes));
}
static bool same(const char *a, const char *b) {
    unsigned diff = 0;
    for (int i = 0; i < 64; i++)
        diff |= (unsigned char)a[i] ^ (unsigned char)b[i];
    return diff == 0;
}
bool mochi_education_active(void) { return atomic_load(&active); }
bool mochi_education_blocked(void) {
    return mochi_education_active() && (options_open || atomic_load(&quick_page) != QUICK_CLOSED ||
        (mochi_lessons_interacting() && !mochi_lessons_voice_passthrough() &&
         !mochi_runtime_education_narrating()));
}
bool mochi_education_voice_allowed(void) { return mochi_education_policy_voice(); }
bool mochi_education_practice_allowed(void) { return mochi_education_policy_practice(); }
bool mochi_education_share_practice(void) { return mochi_education_policy_share(); }
void mochi_education_apply_settings(const cJSON *settings, double server_time) {
    mochi_education_policy_apply(settings, server_time);
}
bool mochi_education_credentials(char *url, size_t u, char *token, size_t t) {
    if (!mochi_education_active() || !mutex || mochi_lessons_network_paused())
        return false;
    xSemaphoreTake(mutex, portMAX_DELAY);
    snprintf(url, u, "%s", settings.url);
    snprintf(token, t, "%s", settings.token);
    bool ready = settings.token[0];
    xSemaphoreGive(mutex);
    return ready;
}
bool mochi_education_enter(void) {
    if (!settings.url[0] || !settings.pin_hash[0]) {
        mochi_show_notice("Peluqo aun sin configurar", 3000);
        return false;
    }
    mochi_voice_cancel();
    settings.enabled = true;
    save();
    atomic_store(&active, true);
    atomic_store(&online, false);
    options_open = false;
    atomic_store(&quick_page, QUICK_CLOSED);
    return true;
}
void mochi_education_state(mochi_state_t mood) {
    mochi_lessons_voice_state(mood);
    if (mutex && xSemaphoreTake(mutex, 0) == pdTRUE) {
        view.mood = mood;
        xSemaphoreGive(mutex);
    }
}
static void status(const char *text) {
    xSemaphoreTake(mutex, portMAX_DELAY);
    snprintf(view.status, sizeof(view.status), "%s", text);
    xSemaphoreGive(mutex);
}
bool mochi_education_console(const char *line) {
    if (!strcmp(line, "@education-policy")) {
        mochi_education_policy_diagnose();
        return true;
    }
    if (!strcmp(line, "@lesson-scene")) {
        mochi_lesson_scene_diagnose();
        return true;
    }
    if (mochi_lessons_console(line))
        return true;
    if (!strncmp(line, "@peluqo-config ", 15)) {
        if (mochi_voice_busy() || mochi_education_active()) {
            printf("@peluqo_config ready=0 busy=1\n");
            return true;
        }
        char url[256], key[65], adult_pin[65];
        if (sscanf(line + 15, "%255s %64s %64s", url, key, adult_pin) == 3 && strlen(key) >= 32 &&
            strlen(adult_pin) >= 6 && strlen(adult_pin) <= 12 &&
            strspn(adult_pin, "0123456789") == strlen(adult_pin) && !strncmp(url, "http", 4)) {
            memset(&settings, 0, sizeof(settings));
            snprintf(settings.url, sizeof(settings.url), "%s", url);
            snprintf(settings.provision, sizeof(settings.provision), "%s", key);
            uint32_t random[4];
            esp_fill_random(random, sizeof(random));
            for (int i = 0; i < 4; i++)
                snprintf(settings.salt + i * 8, 9, "%08lx", (unsigned long)random[i]);
            char material[112];
            snprintf(material, sizeof(material), "%s:%s", settings.salt, adult_pin);
            digest(material, settings.pin_hash);
            memset(material, 0, sizeof(material));
            save();
            printf("@peluqo_config ready=1\n");
        } else
            printf("@peluqo_config ready=0 invalid=1\n");
        memset(key, 0, sizeof(key));
        memset(adult_pin, 0, sizeof(adult_pin));
        return true;
    }
    if (!strcmp(line, "@peluqo")) {
        mochi_education_enter();
        printf("@peluqo active=%d\n", mochi_education_active());
        return true;
    }
    if (!strcmp(line, "@peluqo-status")) {
        mochi_options_t options;
        mochi_options_get(&options);
        printf("@peluqo active=%d paired=%d mic=%d busy=%d options=%d menu=%d volume=%d\n", mochi_education_active(),
               settings.token[0] != 0, options.microphone, mochi_voice_busy(), options_open,
               atomic_load(&quick_page), mochi_audio_get_volume());
        return true;
    }
    return false;
}
static cJSON *exchange(const char *route, const char *body, bool bootstrap, int *http) {
    if (mochi_lessons_network_paused()) {
        *http = 0;
        return NULL;
    }
    char url[256], token[65];
    xSemaphoreTake(mutex, portMAX_DELAY);
    snprintf(url, sizeof(url), "%s", settings.url);
    snprintf(token, sizeof(token), "%s", bootstrap ? settings.provision : settings.token);
    xSemaphoreGive(mutex);
    char *response = heap_caps_calloc(1, 16384, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!response)
        return NULL;
    esp_err_t r = mochi_runtime_education_json(url, token, route, body, response, 16384, http);
    memset(token, 0, sizeof(token));
    cJSON *parsed = r == ESP_OK && *http == 200 ? cJSON_Parse(response) : NULL;
    memset(response, 0, 16384);
    free(response);
    return parsed;
}
static const char *text(cJSON *j, const char *key) {
    cJSON *v = cJSON_GetObjectItemCaseSensitive(j, key);
    return cJSON_IsString(v) ? v->valuestring : "";
}
static void worker(void *unused) {
    (void)unused;
    unsigned backoff = 2;
    int64_t pair_deadline = 0;
    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(backoff * 1000));
        if (!mochi_education_active())
            continue;
        if (mochi_lessons_network_paused()) {
            status("Prueba sin red educativa. Actividad local disponible.");
            backoff = 2;
            continue;
        }
        int http = 0;
        if (atomic_load(&renewing)) {
            cJSON *revoked =
                settings.token[0] ? exchange("/v1/education/unpair", "{}", false, &http) : NULL;
            if ((!settings.token[0] || revoked || http == 401 || http == 404) &&
                mochi_lessons_forget()) {
                mochi_voice_cancel();
                xSemaphoreTake(mutex, portMAX_DELAY);
                memset(settings.token, 0, sizeof(settings.token));
                memset(&view, 0, sizeof(view));
                snprintf(view.name, sizeof(view.name), "Peluqo");
                xSemaphoreGive(mutex);
                save();
                atomic_store(&renewing, false);
                pair_deadline = 0;
                backoff = 2;
            } else {
                status("Necesito conexion para renovar el vinculo");
                backoff = 10;
            }
            cJSON_Delete(revoked);
            continue;
        }
        if (!settings.token[0]) {
            if (!view.pending[0] || esp_timer_get_time() > pair_deadline) {
                cJSON *j = exchange("/v1/education/pair/start", "{}", true, &http);
                if (!j) {
                    status("No puedo conectar. Reintentando");
                    backoff = backoff < 30 ? backoff * 2 : 30;
                    continue;
                }
                xSemaphoreTake(mutex, portMAX_DELAY);
                snprintf(view.code, sizeof(view.code), "%s", text(j, "code"));
                snprintf(view.pending, sizeof(view.pending), "%s", text(j, "pending"));
                xSemaphoreGive(mutex);
                cJSON_Delete(j);
                pair_deadline = esp_timer_get_time() + 300000000;
                status("Introduce este codigo en la web");
            }
            char body[160];
            snprintf(body, sizeof(body), "{\"pending\":\"%s\"}", view.pending);
            cJSON *j = exchange("/v1/education/pair/status", body, true, &http);
            if (j && cJSON_IsTrue(cJSON_GetObjectItem(j, "paired"))) {
                const char *token = text(j, "token");
                if (strlen(token) >= 32 && strlen(token) < sizeof(settings.token)) {
                    xSemaphoreTake(mutex, portMAX_DELAY);
                    snprintf(settings.token, sizeof(settings.token), "%s", token);
                    view.code[0] = view.pending[0] = 0;
                    xSemaphoreGive(mutex);
                    save();
                    status("Vinculado. Activa una mision en la web");
                }
            }
            cJSON_Delete(j);
            backoff = 2;
            continue;
        }
        cJSON *j = exchange("/v1/education/events", "{}", false, &http);
        atomic_store(&online, j != NULL);
        mochi_lessons_connection(j != NULL);
        if (!j) {
            if (http == 401 || http == 404) {
                /* An explicit online denial revokes access to cached work too.
                 * Network failures keep the downloaded task available offline. */
                mochi_lessons_forget();
                mochi_voice_cancel();
                xSemaphoreTake(mutex, portMAX_DELAY);
                view.session[0] = 0;
                snprintf(view.name, sizeof(view.name), "Peluqo");
                xSemaphoreGive(mutex);
            }
            status(http == 401 || http == 404 ? "Vinculo no autorizado. Consulta al adulto"
                                              : "Sin conexion. Solo las misiones descargadas siguen disponibles.");
            backoff = backoff < 30 ? backoff * 2 : 30;
            continue;
        }
        backoff = 2;
        cJSON *server_time = cJSON_GetObjectItemCaseSensitive(j, "serverTime");
        mochi_education_apply_settings(cJSON_GetObjectItemCaseSensitive(j, "deviceSettings"),
            cJSON_IsNumber(server_time) ? server_time->valuedouble : 0);
        /* Fetch adult controls before attempting any queued upload. The backend
         * independently checks consent, including a change made while offline. */
        cJSON *pending_result = mochi_lessons_pending_result();
        if (pending_result) {
            char *body = cJSON_PrintUnformatted(pending_result);
            if (body) {
                cJSON *received = exchange("/v1/education/result", body, false, &http);
                if (received && cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(received, "accepted")) &&
                    !strcmp(text(received, "resultId"), text(pending_result, "resultId")))
                    mochi_lessons_acknowledge(text(received, "resultId"));
                cJSON_Delete(received);
                cJSON_free(body);
            }
            cJSON_Delete(pending_result);
        }
        mochi_lessons_offer(cJSON_GetObjectItemCaseSensitive(j, "localLesson"));
        const char *session = text(j, "sessionId");
        xSemaphoreTake(mutex, portMAX_DELAY);
        bool changed = strcmp(view.session, session) != 0;
        snprintf(view.session, sizeof(view.session), "%s", session);
        cJSON *p = cJSON_GetObjectItem(j, "companion");
        if (cJSON_IsObject(p)) {
            snprintf(view.name, sizeof(view.name), "%s", text(p, "name"));
        }
        xSemaphoreGive(mutex);
        if (changed)
            mochi_voice_cancel();
        if (!session[0] && cJSON_IsObject(cJSON_GetObjectItemCaseSensitive(j, "localLesson")))
            status("Tu misión está lista. Puedes abrirla aquí.");
        else if (!session[0])
            status("Listo. Tu docente debe activar una sesion");
        else if (changed)
            status("Exploramos juntos. Manten para preguntar");
        cJSON *events = cJSON_GetObjectItem(j, "events"), *event = NULL;
        uint64_t seq = 0;
        cJSON_ArrayForEach(event, events) {
            cJSON *payload = cJSON_GetObjectItem(event, "payload");
            const char *phrase = text(payload, "text");
            mochi_education_state(!strcmp(text(payload, "mood"), "think")       ? MOCHI_THINKING
                                  : !strcmp(text(payload, "mood"), "encourage") ? MOCHI_CURIOUS
                                                                                : MOCHI_HAPPY);
            atomic_store(&reaction_pending, true);
            mochi_display_activity();
            if (phrase[0])
                status(phrase);
            double n = cJSON_GetNumberValue(cJSON_GetObjectItem(event, "seq"));
            if (n > seq)
                seq = (uint64_t)n;
            /* Speak the most recent current-session event only. The server rejects
             * stale events and revalidates the binding after synthesizing audio. */
            if (!cJSON_GetArrayItem(events, cJSON_GetArraySize(events) - 1) ||
                event == cJSON_GetArrayItem(events, cJSON_GetArraySize(events) - 1))
                if (phrase[0] && !changed && mochi_education_voice_allowed())
                    mochi_runtime_education_say(text(event, "id"));
        }
        if (seq && session[0]) {
            char body[160];
            snprintf(body, sizeof(body), "{\"sessionId\":\"%s\",\"seq\":%llu}", session,
                     (unsigned long long)seq);
            int code = 0;
            cJSON_Delete(exchange("/v1/education/ack", body, false, &code));
        }
        cJSON_Delete(j);
    }
}
static lv_obj_t *label(lv_obj_t *parent, const char *value, int y, int width) {
    lv_obj_t *o = lv_label_create(parent);
    lv_label_set_text(o, value);
    lv_obj_set_width(o, width);
    lv_obj_align(o, LV_ALIGN_TOP_MID, 0, y);
    lv_obj_set_style_text_align(o, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_set_style_text_font(o, &mochi_font_16, 0);
    lv_obj_set_style_text_color(o, lv_color_hex(0xD3D6DE), 0);
    return o;
}
void mochi_education_options(void) {
    if (!screen || !mochi_education_active())
        return;
    mochi_voice_cancel();
    options_open = false;
    lv_obj_add_flag(panel, LV_OBJ_FLAG_HIDDEN);
    quick_show(QUICK_HOME);
}
static bool authorize_adult(void) {
    static int64_t blocked;
    static unsigned attempts;
    if (esp_timer_get_time() < blocked) {
        lv_label_set_text(pin_hint, "Espera un minuto para reintentar");
        return false;
    }
    char material[112], value[65];
    snprintf(material, sizeof(material), "%s:%s", settings.salt, lv_textarea_get_text(pin));
    digest(material, value);
    memset(material, 0, sizeof(material));
    lv_textarea_set_text(pin, "");
    bool valid = same(value, settings.pin_hash);
    memset(value, 0, sizeof(value));
    if (valid) {
        attempts = 0;
        return true;
    }
    attempts++;
    if (attempts >= 5) {
        blocked = esp_timer_get_time() + 60000000;
        attempts = 0;
    }
    lv_label_set_text(pin_hint, "Clave de adulto no valida");
    return false;
}
static void unlock(lv_event_t *e) {
    (void)e;
    if (!authorize_adult())
        return;
    mochi_voice_cancel();
    settings.enabled = false;
    save();
    atomic_store(&active, false);
    atomic_store(&online, false);
    options_open = false;
    lv_obj_add_flag(panel, LV_OBJ_FLAG_HIDDEN);
}
static void renew(lv_event_t *e) {
    (void)e;
    if (!authorize_adult())
        return;
    mochi_voice_cancel();
    atomic_store(&renewing, true);
    atomic_store(&online, false);
    options_open = false;
    lv_obj_add_flag(panel, LV_OBJ_FLAG_HIDDEN);
    status("Renovando el vinculo educativo");
}
static void back(lv_event_t *e) {
    (void)e;
    lv_textarea_set_text(pin, "");
    options_open = false;
    lv_obj_add_flag(panel, LV_OBJ_FLAG_HIDDEN);
}
static lv_obj_t *button(lv_obj_t *parent, const char *value, int y, lv_event_cb_t cb) {
    lv_obj_t *b = lv_button_create(parent);
    lv_obj_set_size(b, 220, 42);
    lv_obj_align(b, LV_ALIGN_TOP_MID, 0, y);
    lv_obj_set_style_bg_color(b, lv_color_hex(0x232631), 0);
    lv_obj_set_style_border_width(b, 1, 0);
    lv_obj_set_style_border_color(b, lv_color_black(), 0);
    lv_obj_set_style_shadow_width(b, 0, 0);
    lv_obj_t *l = label(b, value, 9, 210);
    lv_obj_center(l);
    lv_obj_add_event_cb(b, cb, LV_EVENT_CLICKED, NULL);
    return b;
}
static void sound_refresh(void) {
    int volume = mochi_audio_get_volume();
    if (volume > 0)
        unmuted_volume = volume;
    lv_label_set_text_fmt(sound_value, "%d%%", volume);
    lv_label_set_text(lv_obj_get_child(sound_mute, 0), volume ? "Silenciar" : "Activar sonido");
    lv_label_set_text(sound_hint, mochi_education_policy_voice()
        ? "Solo cambia el sonido de Mochi."
        : "La voz sigue según los límites\ny ajustes de tu adulto.");
}
static void quick_show(int page) {
    atomic_store(&quick_page, page);
    if (!quick_panel && page != QUICK_CLOSED)
        create_quick_menu();
    if (!quick_panel)
        return;
    if (page == QUICK_CLOSED) {
        lv_obj_add_flag(quick_panel, LV_OBJ_FLAG_HIDDEN);
        return;
    }
    lv_obj_remove_flag(quick_panel, LV_OBJ_FLAG_HIDDEN);
    if (page == QUICK_SOUND) {
        lv_obj_add_flag(quick_home, LV_OBJ_FLAG_HIDDEN);
        lv_obj_remove_flag(quick_sound, LV_OBJ_FLAG_HIDDEN);
        sound_refresh();
    } else {
        lv_obj_remove_flag(quick_home, LV_OBJ_FLAG_HIDDEN);
        lv_obj_add_flag(quick_sound, LV_OBJ_FLAG_HIDDEN);
    }
    lv_obj_move_foreground(quick_panel);
    mochi_display_activity();
}
static void quick_action(lv_event_t *event) {
    intptr_t action = (intptr_t)lv_event_get_user_data(event);
    mochi_display_activity();
    if (action == 0)
        quick_show(QUICK_CLOSED);
    else if (action == 1)
        quick_show(QUICK_SOUND);
    else if (action == 2) {
        quick_show(QUICK_CLOSED);
        options_open = true;
        lv_textarea_set_text(pin, "");
        lv_label_set_text(pin_hint, "");
        lv_obj_remove_flag(panel, LV_OBJ_FLAG_HIDDEN);
        lv_obj_move_foreground(panel);
    } else if (action == 3)
        quick_show(QUICK_HOME);
    else if (action == 7)
        mochi_education_options();
    else if (action >= 4 && action <= 6) {
        int volume = mochi_audio_get_volume();
        if (volume > 0)
            unmuted_volume = volume;
        if (action == 6)
            volume = volume ? 0 : unmuted_volume;
        else
            volume += action == 4 ? -10 : 10;
        /* The existing controls worker persists audio volume in mochi_ui after
         * its 700 ms debounce, also used by the original personal audio UI. */
        mochi_audio_set_volume(volume);
        sound_refresh();
    }
}
static lv_obj_t *quick_button(lv_obj_t *parent, const char *text, int x, int y, int width, int action) {
    lv_obj_t *object = lv_button_create(parent);
    lv_obj_set_size(object, width, 48);
    lv_obj_align(object, LV_ALIGN_TOP_MID, x, y);
    lv_obj_set_style_bg_color(object, lv_color_hex(0x18362E), 0);
    lv_obj_set_style_bg_color(object, lv_color_hex(0x31594A), LV_STATE_PRESSED);
    lv_obj_set_style_border_color(object, lv_color_hex(0x6CA888), 0);
    lv_obj_set_style_border_width(object, 1, 0);
    lv_obj_set_style_radius(object, 14, 0);
    lv_obj_set_style_shadow_width(object, 0, 0);
    lv_obj_remove_flag(object, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_event_cb(object, quick_action, LV_EVENT_CLICKED, (void *)(intptr_t)action);
    lv_obj_t *caption = label(object, text, 0, width - 12);
    lv_obj_set_style_text_font(caption, &mochi_font_16, 0);
    lv_obj_center(caption);
    return object;
}
static void create_quick_menu(void) {
    quick_panel = lv_obj_create(screen);
    lv_obj_remove_style_all(quick_panel);
    lv_obj_set_size(quick_panel, 466, 466);
    lv_obj_set_style_bg_color(quick_panel, lv_color_black(), 0);
    lv_obj_set_style_bg_opa(quick_panel, LV_OPA_COVER, 0);
    lv_obj_remove_flag(quick_panel, LV_OBJ_FLAG_SCROLLABLE);
    quick_home = lv_obj_create(quick_panel);
    quick_sound = lv_obj_create(quick_panel);
    lv_obj_t *pages[] = {quick_home, quick_sound};
    for (unsigned i = 0; i < 2; i++) {
        lv_obj_remove_style_all(pages[i]);
        lv_obj_set_size(pages[i], 466, 466);
        lv_obj_remove_flag(pages[i], LV_OBJ_FLAG_CLICKABLE | LV_OBJ_FLAG_SCROLLABLE);
    }
    lv_obj_t *title = label(quick_home, "Nuestro menú", 94, 280);
    lv_obj_set_style_text_font(title, &mochi_font_20, 0);
    label(quick_home, "Ajustes sencillos", 130, 280);
    quick_button(quick_home, "Sonido", 0, 184, 230, 1);
    quick_button(quick_home, "Controles del adulto", 0, 244, 230, 2);
    lv_obj_t *identity = label(quick_home, "Soy un compañero de IA.\nPuedo equivocarme.", 308, 280);
    lv_obj_set_style_text_font(identity, &mochi_font_14, 0);
    quick_button(quick_home, "Volver", 0, 366, 180, 0);
    title = label(quick_sound, "Sonido", 94, 280);
    lv_obj_set_style_text_font(title, &mochi_font_20, 0);
    label(quick_sound, "El volumen de Mochi", 132, 280);
    sound_value = label(quick_sound, "", 174, 220);
    lv_obj_set_style_text_font(sound_value, &mochi_font_20, 0);
    quick_button(quick_sound, "-10", -80, 218, 112, 4);
    quick_button(quick_sound, "+10", 80, 218, 112, 5);
    sound_mute = quick_button(quick_sound, "Silenciar", 0, 282, 230, 6);
    sound_hint = label(quick_sound, "", 342, 290);
    lv_obj_set_style_text_font(sound_hint, &mochi_font_14, 0);
    quick_button(quick_sound, "Volver", 0, 390, 180, 3);
    lv_obj_add_flag(quick_panel, LV_OBJ_FLAG_HIDDEN);
    lv_obj_add_flag(quick_sound, LV_OBJ_FLAG_HIDDEN);
}
static void create_reminder_toast(void) {
    reminder_toast = lv_obj_create(screen);
    lv_obj_remove_style_all(reminder_toast);
    lv_obj_set_size(reminder_toast, 316, 88);
    lv_obj_align(reminder_toast, LV_ALIGN_TOP_MID, 0, 122);
    lv_obj_set_style_bg_color(reminder_toast, lv_color_hex(0x193B32), 0);
    lv_obj_set_style_bg_opa(reminder_toast, LV_OPA_COVER, 0);
    lv_obj_set_style_border_color(reminder_toast, lv_color_hex(0x8CC2A6), 0);
    lv_obj_set_style_border_width(reminder_toast, 1, 0);
    lv_obj_set_style_radius(reminder_toast, 18, 0);
    lv_obj_remove_flag(reminder_toast, LV_OBJ_FLAG_CLICKABLE | LV_OBJ_FLAG_SCROLLABLE);
    reminder_label = label(reminder_toast, "", 10, 288);
    lv_obj_set_height(reminder_label, 68);
    lv_label_set_long_mode(reminder_label, LV_LABEL_LONG_MODE_WRAP);
    lv_obj_set_style_text_font(reminder_label, &mochi_font_16, 0);
    lv_obj_remove_flag(reminder_label, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_add_flag(reminder_toast, LV_OBJ_FLAG_HIDDEN);
}
static void reminder_tick(bool permitted_to_show) {
    if (!reminder_toast)
        return;
    int64_t now = esp_timer_get_time();
    int64_t delta = reminder_at ? now - reminder_at : 0;
    reminder_at = now;
    if (!mochi_education_active() || !mochi_education_policy_practice()) {
        reminder_left = 0;
        lv_obj_add_flag(reminder_toast, LV_OBJ_FLAG_HIDDEN);
        return;
    }
    if (!permitted_to_show) {
        lv_obj_add_flag(reminder_toast, LV_OBJ_FLAG_HIDDEN);
        return;
    }
    if (reminder_left > 0)
        reminder_left = delta < reminder_left ? reminder_left - delta : 0;
    if (!reminder_left) {
        char text[160];
        if (mochi_education_policy_next_reminder(text, sizeof(text))) {
            lv_label_set_text(reminder_label, text);
            reminder_left = 6000000;
        }
    }
    if (reminder_left > 0) {
        lv_obj_remove_flag(reminder_toast, LV_OBJ_FLAG_HIDDEN);
        lv_obj_move_foreground(reminder_toast);
    } else
        lv_obj_add_flag(reminder_toast, LV_OBJ_FLAG_HIDDEN);
}
static void close_conversation(lv_event_t *event) {
    (void)event;
    mochi_voice_cancel();
    atomic_store(&conversation_open, false);
    xSemaphoreTake(mutex, portMAX_DELAY);
    if (conversation_text)
        memset(conversation_text, 0, 2801);
    conversation_revision++;
    xSemaphoreGive(mutex);
    mochi_display_activity();
}
static void conversation_tick(bool visible) {
    if (!conversation_panel)
        return;
    bool captions = mochi_education_policy_captions();
    if (!captions && atomic_exchange(&conversation_open, false)) {
        xSemaphoreTake(mutex, portMAX_DELAY);
        if (conversation_text)
            memset(conversation_text, 0, 2801);
        xSemaphoreGive(mutex);
    }
    bool open = visible && atomic_load(&conversation_open) && captions;
    if (!open) {
        lv_obj_add_flag(conversation_panel, LV_OBJ_FLAG_HIDDEN);
        return;
    }
    lv_obj_remove_flag(conversation_panel, LV_OBJ_FLAG_HIDDEN);
    xSemaphoreTake(mutex, portMAX_DELAY);
    if (conversation_text && conversation_rendered != conversation_revision) {
        lv_label_set_text(conversation_label, conversation_text);
        lv_obj_scroll_to_y(conversation_scroll, 0, LV_ANIM_OFF);
        conversation_rendered = conversation_revision;
    }
    xSemaphoreGive(mutex);
}
static void tick(lv_timer_t *timer) {
    (void)timer;
    static bool engaged_before;
    /* Screen time includes the home, reading and sound screens too. A sleeping
     * display consumes no allowance; active voice remains an educational use. */
    bool engaged = mochi_education_active() && (mochi_display_awake() || mochi_voice_busy());
    mochi_education_policy_tick(engaged);
    if (engaged_before && !engaged)
        mochi_education_policy_flush();
    engaged_before = engaged;
    if (!mochi_education_active()) {
        if (atomic_exchange(&conversation_open, false)) {
            xSemaphoreTake(mutex, portMAX_DELAY);
            if (conversation_text)
                memset(conversation_text, 0, 2801);
            xSemaphoreGive(mutex);
        }
        conversation_tick(false);
        mochi_lessons_tick(false);
        quick_show(QUICK_CLOSED);
        reminder_tick(false);
        lv_obj_add_flag(screen, LV_OBJ_FLAG_HIDDEN);
        return;
    }
    lv_obj_remove_flag(screen, LV_OBJ_FLAG_HIDDEN);
    bool covered = options_open || atomic_load(&quick_page) != QUICK_CLOSED;
    mochi_lessons_tick(!covered);
    conversation_tick(!covered);
    bool lesson_open = mochi_lessons_interacting() && !covered;
    if (lesson_open || covered) {
        lv_obj_add_flag(name_label, LV_OBJ_FLAG_HIDDEN);
        lv_obj_add_flag(status_label, LV_OBJ_FLAG_HIDDEN);
        lv_obj_add_flag(code_label, LV_OBJ_FLAG_HIDDEN);
    } else {
        lv_obj_remove_flag(name_label, LV_OBJ_FLAG_HIDDEN);
        lv_obj_remove_flag(status_label, LV_OBJ_FLAG_HIDDEN);
        lv_obj_remove_flag(code_label, LV_OBJ_FLAG_HIDDEN);
    }
    if (atomic_load(&quick_page) == QUICK_SOUND)
        sound_refresh();
    reminder_tick(!covered && !mochi_voice_busy() && mochi_display_awake());
    if (covered)
        return;
    view_t v;
    bool paired;
    xSemaphoreTake(mutex, portMAX_DELAY);
    v = view;
    paired = settings.token[0] != 0;
    xSemaphoreGive(mutex);
    mochi_options_t audio_options;
    mochi_options_get(&audio_options);
    bool voice_enabled = mochi_education_policy_voice();
    lv_label_set_text(name_label, v.session[0] ? v.name : "Nuestro rincón");
    char transient[160] = {0};
    xSemaphoreTake(mutex, portMAX_DELAY);
    if (notice_text[0] && (!notice_until || esp_timer_get_time() < notice_until))
        snprintf(transient, sizeof(transient), "%s", notice_text);
    xSemaphoreGive(mutex);
    const char *caption = !mochi_education_practice_allowed() ? mochi_education_policy_notice()
                          : transient[0] ? transient
                          : mochi_voice_busy()
                              ? (v.mood == MOCHI_LISTENING  ? "Te escucho. Suelta al terminar."
                                 : v.mood == MOCHI_SPEAKING ? "Te lo cuento..."
                                                            : "Buscando en los materiales...")
                              : !audio_options.microphone ? "Micrófono desactivado"
                              : !voice_enabled ? "Voz desactivada por tu adulto"
                              : atomic_load(&online) && paired
                                  ? "Mantén pulsado a Mochi\npara hablar" : v.status;
    lv_label_set_text(status_label, caption);
    lv_label_set_text(code_label, v.code);
    if (!mochi_voice_busy() && atomic_exchange(&reaction_pending, false))
        mochi_set_state(v.mood, 2000);
}
void mochi_education_create(lv_obj_t *parent) {
    mutex = xSemaphoreCreateMutex();
    if (!mutex)
        return;
    mochi_education_policy_init();
    nvs_handle_t n;
    if (nvs_open("peluqo", NVS_READONLY, &n) == ESP_OK) {
        size_t size = sizeof(settings);
        if (nvs_get_blob(n, "settings", &settings, &size) != ESP_OK || size != sizeof(settings))
            memset(&settings, 0, sizeof(settings));
        nvs_close(n);
    }
    settings.url[sizeof(settings.url) - 1] = 0;
    settings.provision[sizeof(settings.provision) - 1] = 0;
    settings.token[sizeof(settings.token) - 1] = 0;
    settings.salt[sizeof(settings.salt) - 1] = 0;
    settings.pin_hash[sizeof(settings.pin_hash) - 1] = 0;
    if (strlen(settings.pin_hash) != 64 || strlen(settings.provision) < 32 || !settings.url[0])
        settings.enabled = false;
    atomic_store(&active, settings.enabled);
    screen = lv_obj_create(parent);
    lv_obj_remove_style_all(screen);
    lv_obj_set_size(screen, 466, 466);
    lv_obj_set_style_bg_opa(screen, LV_OPA_TRANSP, 0);
    // Leave the original touch surface and settings button reachable.
    lv_obj_remove_flag(screen, LV_OBJ_FLAG_SCROLLABLE | LV_OBJ_FLAG_CLICKABLE);
    name_label = label(screen, "Nuestro rincón", 88, 260);
    lv_obj_set_style_text_font(name_label, &mochi_font_14, 0);
    lv_obj_set_height(name_label, 20);
    lv_label_set_long_mode(name_label, LV_LABEL_LONG_MODE_DOTS);
    code_label = label(screen, "", 350, 220);
    status_label = label(screen, view.status, 414, 196);
    lv_obj_set_style_text_font(status_label, &mochi_font_14, 0);
    lv_obj_set_height(status_label, 32);
    lv_label_set_long_mode(status_label, LV_LABEL_LONG_MODE_WRAP);
    lv_obj_set_style_bg_color(status_label, lv_color_black(), 0);
    lv_obj_set_style_bg_opa(status_label, LV_OPA_COVER, 0);
    mochi_lessons_create(screen);
    /* Dedicated reading surface for daily conversation without a task. It
     * remains open after audio ends and captures its own touch scrolling. */
    conversation_text = heap_caps_calloc(2801, 1, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    conversation_panel = lv_obj_create(screen);
    lv_obj_remove_style_all(conversation_panel);
    lv_obj_set_size(conversation_panel, 466, 466);
    lv_obj_set_style_bg_color(conversation_panel, lv_color_black(), 0);
    lv_obj_set_style_bg_opa(conversation_panel, LV_OPA_COVER, 0);
    lv_obj_remove_flag(conversation_panel, LV_OBJ_FLAG_SCROLLABLE);
    label(conversation_panel, "Mochi te cuenta", 99, 270);
    conversation_scroll = lv_obj_create(conversation_panel);
    lv_obj_remove_style_all(conversation_scroll);
    lv_obj_set_size(conversation_scroll, 306, 200);
    lv_obj_align(conversation_scroll, LV_ALIGN_TOP_MID, 0, 140);
    lv_obj_set_style_pad_left(conversation_scroll, 4, 0);
    lv_obj_set_style_pad_right(conversation_scroll, 12, 0);
    lv_obj_set_scroll_dir(conversation_scroll, LV_DIR_VER);
    lv_obj_set_scrollbar_mode(conversation_scroll, LV_SCROLLBAR_MODE_AUTO);
    lv_obj_set_style_bg_color(conversation_scroll, lv_color_hex(0x60836E), LV_PART_SCROLLBAR);
    lv_obj_set_style_width(conversation_scroll, 3, LV_PART_SCROLLBAR);
    conversation_label = lv_label_create(conversation_scroll);
    lv_obj_set_width(conversation_label, 284);
    lv_label_set_long_mode(conversation_label, LV_LABEL_LONG_MODE_WRAP);
    lv_obj_set_style_text_font(conversation_label, &mochi_font_16, 0);
    lv_obj_set_style_text_line_space(conversation_label, 4, 0);
    lv_obj_set_style_text_color(conversation_label, lv_color_hex(0xE4EBE3), 0);
    lv_label_set_text(conversation_label, "");
    lv_obj_remove_flag(conversation_label, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_t *scroll_hint = label(conversation_panel, "Desliza para leer la respuesta completa", 347, 300);
    lv_obj_set_style_text_font(scroll_hint, &mochi_font_14, 0);
    lv_obj_t *close_caption = button(conversation_panel, "Volver", 376, close_conversation);
    lv_obj_set_size(close_caption, 180, 44);
    /* The full reading surface covers the original gear. Keep the same safe
     * top-right target available for sound without closing a saved caption. */
    quick_button(conversation_panel, LV_SYMBOL_SETTINGS, 104, 59, 48, 7);
    lv_obj_add_flag(conversation_panel, LV_OBJ_FLAG_HIDDEN);
    panel = lv_obj_create(screen);
    lv_obj_remove_style_all(panel);
    lv_obj_set_size(panel, 466, 466);
    lv_obj_set_style_bg_color(panel, lv_color_black(), 0);
    lv_obj_set_style_bg_opa(panel, LV_OPA_COVER, 0);
    lv_obj_remove_flag(panel, LV_OBJ_FLAG_SCROLLABLE);
    label(panel, "Opciones del adulto", 63, 260);
    pin_hint = label(panel, "", 85, 300);
    lv_obj_set_style_text_font(pin_hint, &mochi_font_14, 0);
    pin = lv_textarea_create(panel);
    lv_obj_set_size(pin, 260, 45);
    lv_obj_align(pin, LV_ALIGN_TOP_MID, 0, 105);
    lv_textarea_set_one_line(pin, true);
    lv_textarea_set_password_mode(pin, true);
    lv_textarea_set_max_length(pin, 64);
    lv_obj_set_style_text_font(pin, &mochi_font_16, 0);
    keyboard = lv_keyboard_create(panel);
    lv_obj_set_size(keyboard, 330, 124);
    lv_obj_align(keyboard, LV_ALIGN_TOP_MID, 0, 155);
    lv_keyboard_set_textarea(keyboard, pin);
    lv_keyboard_set_mode(keyboard, LV_KEYBOARD_MODE_NUMBER);
    button(panel, "Volver a Mochi", 290, unlock);
    button(panel, "Renovar vinculo", 338, renew);
    button(panel, "Seguir aprendiendo", 386, back);
    lv_obj_add_flag(panel, LV_OBJ_FLAG_HIDDEN);
    create_reminder_toast();
    lv_obj_add_flag(screen, LV_OBJ_FLAG_HIDDEN);
    lv_timer_create(tick, 50, NULL);
    xTaskCreate(worker, "peluqo", 8192, NULL, 3, NULL);
}
