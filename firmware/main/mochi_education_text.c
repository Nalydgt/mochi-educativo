/* Deliberate written conversation. No microphone, audio, NVS or transcript log. */
#include "mochi_education_text.h"
#include "mochi_education.h"
#include "mochi_runtime.h"
#include "mochi_display.h"
#include "mochi_fonts.h"
#include "cJSON.h"
#include "esp_heap_caps.h"
#include "esp_random.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { MESSAGE_BYTES = 481, REPLY_BYTES = 2801 };
typedef struct { char question[MESSAGE_BYTES], token[65], url[256]; unsigned epoch; } text_job_t;
static lv_obj_t *surface, *input, *keys, *hint, *reader, *reply_label, *again;
static SemaphoreHandle_t guard;
static char *reply_text;
static atomic_bool opened, busy;
static unsigned epoch, revision, rendered;
static bool upper, numbers, showing_reply, request_succeeded;
static const char *const lower_keys[] = {
    "a","b","c","d","e","f","g","\n", "h","i","j","k","l","m","n","\n",
    "ñ","o","p","q","r","s","t","\n", "u","v","w","x","y","z",LV_SYMBOL_BACKSPACE,"\n",
    "ABC","123","Espacio","Enviar",""
};
static const char *const upper_keys[] = {
    "A","B","C","D","E","F","G","\n", "H","I","J","K","L","M","N","\n",
    "Ñ","O","P","Q","R","S","T","\n", "U","V","W","X","Y","Z",LV_SYMBOL_BACKSPACE,"\n",
    "abc","123","Espacio","Enviar",""
};
static const char *const number_keys[] = {
    "1","2","3","4","5","6","7","\n", "8","9","0","á","é","í","ó","\n",
    "ú","ü","ñ","¿","?","¡","!","\n", ".",",","-","+","=","/",LV_SYMBOL_BACKSPACE,"\n",
    "abc","123","Espacio","Enviar",""
};

bool mochi_education_text_active(void) { return atomic_load(&opened); }
bool mochi_education_text_busy(void) { return atomic_load(&busy); }

static lv_obj_t *text_label(lv_obj_t *parent, const char *value, int y, int width) {
    lv_obj_t *object = lv_label_create(parent);
    lv_label_set_text(object, value);
    lv_obj_set_width(object, width);
    lv_obj_align(object, LV_ALIGN_TOP_MID, 0, y);
    lv_obj_set_style_text_font(object, &mochi_font_16, 0);
    lv_obj_set_style_text_color(object, lv_color_hex(0xE4EBE3), 0);
    lv_obj_set_style_text_align(object, LV_TEXT_ALIGN_CENTER, 0);
    return object;
}
static void map_keys(void) {
    lv_buttonmatrix_set_map(keys, numbers ? number_keys : upper ? upper_keys : lower_keys);
    lv_buttonmatrix_set_button_width(keys, 30, 3);
    lv_buttonmatrix_set_button_width(keys, 31, 2);
    lv_buttonmatrix_set_button_ctrl_all(keys, LV_BUTTONMATRIX_CTRL_NO_REPEAT);
}
static void compose(void) {
    showing_reply = false;
    lv_obj_remove_flag(input, LV_OBJ_FLAG_HIDDEN);
    lv_obj_remove_flag(keys, LV_OBJ_FLAG_HIDDEN);
    lv_obj_add_flag(reader, LV_OBJ_FLAG_HIDDEN);
    lv_obj_add_flag(again, LV_OBJ_FLAG_HIDDEN);
    lv_label_set_text(hint, "Pulsa Enviar para continuar");
}
static void close_text(lv_event_t *event) {
    (void)event;
    atomic_store(&opened, false);
    xSemaphoreTake(guard, portMAX_DELAY);
    epoch++;
    if (reply_text) memset(reply_text, 0, REPLY_BYTES);
    xSemaphoreGive(guard);
    lv_textarea_set_text(input, "");
    lv_label_set_text(reply_label, "");
    lv_obj_add_flag(surface, LV_OBJ_FLAG_HIDDEN);
    mochi_display_activity();
}
static void next_message(lv_event_t *event) {
    (void)event;
    if (atomic_load(&busy)) return;
    if (request_succeeded) lv_textarea_set_text(input, "");
    compose();
    mochi_display_activity();
}
static void request_text(void *argument) {
    text_job_t *job = argument;
    char identity[37];
    uint32_t random[4]; esp_fill_random(random, sizeof(random));
    snprintf(identity, sizeof(identity), "%08lx%08lx%08lx%08lx", (unsigned long)random[0],
             (unsigned long)random[1], (unsigned long)random[2], (unsigned long)random[3]);
    cJSON *request = cJSON_CreateObject();
    cJSON_AddStringToObject(request, "requestId", identity);
    cJSON_AddStringToObject(request, "question", job->question);
    char *body = cJSON_PrintUnformatted(request);
    cJSON_Delete(request);
    char *output = heap_caps_calloc(8192, 1, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    int status = 0;
    esp_err_t result = body && output ? mochi_runtime_education_json(job->url, job->token,
        "/v1/education/text", body, output, 8192, &status) : ESP_ERR_NO_MEM;
    cJSON *reply = result == ESP_OK && status == 200 ? cJSON_Parse(output) : NULL;
    const cJSON *text = cJSON_GetObjectItemCaseSensitive(reply, "text");
    const cJSON *channel = cJSON_GetObjectItemCaseSensitive(reply, "channel");
    const cJSON *kind = cJSON_GetObjectItemCaseSensitive(reply, "kind");
    bool valid = cJSON_IsString(text) && text->valuestring[0] && strlen(text->valuestring) < REPLY_BYTES &&
                 cJSON_IsString(channel) && !strcmp(channel->valuestring, "text");
    char url[256], token[65];
    bool paired = mochi_education_credentials(url, sizeof(url), token, sizeof(token)) && !strcmp(token, job->token);
    memset(token, 0, sizeof(token));
    xSemaphoreTake(guard, portMAX_DELAY);
    if (opened && job->epoch == epoch && paired && mochi_education_practice_allowed()) {
        snprintf(reply_text, REPLY_BYTES, "%s", valid ? text->valuestring :
            status == 403 ? "Ahora toca descansar. Tu adulto puede revisar el horario y los límites."
            : "Ahora no he podido recibir la respuesta. Tu mensaje sigue preparado para volver a intentarlo.");
        request_succeeded = valid && (!cJSON_IsString(kind) || strcmp(kind->valuestring, "unavailable"));
        revision++;
    }
    xSemaphoreGive(guard);
    cJSON_Delete(reply);
    if (body) { memset(body, 0, strlen(body)); free(body); }
    if (output) { memset(output, 0, 8192); free(output); }
    memset(job, 0, sizeof(*job)); free(job);
    atomic_store(&busy, false);
    vTaskDelete(NULL);
}
static void send_message(void) {
    if (atomic_load(&busy)) return;
    if (!mochi_education_practice_allowed()) {
        lv_label_set_text(hint, "Ahora toca descansar"); return;
    }
    const char *value = lv_textarea_get_text(input);
    bool meaningful = false;
    for (const char *at = value; *at; at++) if (*at != ' ' && *at != '\n' && *at != '\t') meaningful = true;
    if (!meaningful || strlen(value) >= MESSAGE_BYTES) {
        lv_label_set_text(hint, "Escribe un mensaje breve"); return;
    }
    text_job_t *job = calloc(1, sizeof(*job));
    if (!job || !mochi_education_credentials(job->url, sizeof(job->url), job->token, sizeof(job->token))) {
        free(job); lv_label_set_text(hint, "Necesito conexión y un vínculo"); return;
    }
    snprintf(job->question, sizeof(job->question), "%s", value);
    xSemaphoreTake(guard, portMAX_DELAY);
    job->epoch = epoch;
    memset(reply_text, 0, REPLY_BYTES);
    xSemaphoreGive(guard);
    atomic_store(&busy, true);
    if (xTaskCreate(request_text, "mochi_text", 8192, job, 3, NULL) != pdPASS) {
        memset(job, 0, sizeof(*job)); free(job); atomic_store(&busy, false);
        lv_label_set_text(hint, "Espera un momento y reintenta"); return;
    }
    showing_reply = true;
    lv_obj_add_flag(input, LV_OBJ_FLAG_HIDDEN);
    lv_obj_add_flag(keys, LV_OBJ_FLAG_HIDDEN);
    lv_obj_add_flag(again, LV_OBJ_FLAG_HIDDEN);
    lv_obj_remove_flag(reader, LV_OBJ_FLAG_HIDDEN);
    lv_label_set_text(reply_label, "Mochi está pensando...\n\nPuedes volver sin perder tu misión.");
    lv_label_set_text(hint, "");
}
static void key_pressed(lv_event_t *event) {
    if (atomic_load(&busy)) return;
    const char *key = lv_buttonmatrix_get_button_text(keys, lv_buttonmatrix_get_selected_button(keys));
    if (!key) return;
    mochi_display_activity();
    if (!strcmp(key, "ABC") || !strcmp(key, "abc")) { upper = !upper && !numbers; numbers = false; map_keys(); }
    else if (!strcmp(key, "123")) { numbers = !numbers; map_keys(); }
    else if (!strcmp(key, LV_SYMBOL_BACKSPACE)) lv_textarea_delete_char(input);
    else if (!strcmp(key, "Enviar")) send_message();
    else lv_textarea_add_text(input, !strcmp(key, "Espacio") ? " " : key);
    (void)event;
}
void mochi_education_text_show(void) {
    if (!surface || !reply_text || !mochi_education_active()) return;
    if (atomic_load(&busy)) { mochi_education_notice("Espera a que termine el mensaje", 2500); return; }
    if (!mochi_education_practice_allowed()) { mochi_education_notice(mochi_education_policy_notice(), 3000); return; }
    mochi_voice_cancel();
    xSemaphoreTake(guard, portMAX_DELAY);
    epoch++; memset(reply_text, 0, REPLY_BYTES);
    rendered = revision;
    xSemaphoreGive(guard);
    atomic_store(&opened, true);
    lv_textarea_set_text(input, "");
    compose();
    lv_obj_remove_flag(surface, LV_OBJ_FLAG_HIDDEN);
    lv_obj_move_foreground(surface);
    mochi_display_activity();
}
void mochi_education_text_tick(bool enabled) {
    if (!surface) return;
    if (opened && (!enabled || !mochi_education_practice_allowed())) { close_text(NULL); return; }
    if (!opened || !showing_reply) return;
    xSemaphoreTake(guard, portMAX_DELAY);
    if (rendered != revision) {
        lv_label_set_text(reply_label, reply_text);
        lv_label_set_text(lv_obj_get_child(again, 0), request_succeeded ? "Escribir otro mensaje" : "Reintentar mensaje");
        rendered = revision;
        lv_obj_scroll_to_y(reader, 0, LV_ANIM_OFF);
    }
    xSemaphoreGive(guard);
    if (!atomic_load(&busy)) lv_obj_remove_flag(again, LV_OBJ_FLAG_HIDDEN);
}
void mochi_education_text_create(lv_obj_t *parent) {
    guard = xSemaphoreCreateMutex();
    reply_text = heap_caps_calloc(REPLY_BYTES, 1, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!guard || !reply_text) return;
    surface = lv_obj_create(parent);
    lv_obj_remove_style_all(surface);
    lv_obj_set_size(surface, 466, 466);
    lv_obj_set_style_bg_color(surface, lv_color_black(), 0);
    lv_obj_set_style_bg_opa(surface, LV_OPA_COVER, 0);
    lv_obj_remove_flag(surface, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_t *title = text_label(surface, "Escribir a Mochi", 77, 260);
    lv_obj_set_style_text_font(title, &mochi_font_20, 0);
    lv_obj_t *back = lv_button_create(surface);
    lv_obj_set_size(back, 48, 44); lv_obj_set_pos(back, 92, 59);
    lv_obj_t *icon = text_label(back, LV_SYMBOL_LEFT, 0, 36); lv_obj_center(icon);
    lv_obj_set_style_bg_color(back, lv_color_hex(0x18362E), 0);
    lv_obj_set_style_shadow_width(back, 0, 0);
    lv_obj_add_event_cb(back, close_text, LV_EVENT_CLICKED, NULL);
    input = lv_textarea_create(surface);
    lv_obj_set_size(input, 310, 62); lv_obj_align(input, LV_ALIGN_TOP_MID, 0, 112);
    lv_textarea_set_max_length(input, 120);
    lv_textarea_set_placeholder_text(input, "Hoy aprendí...");
    lv_obj_set_style_text_font(input, &mochi_font_16, 0);
    lv_obj_set_style_text_color(input, lv_color_hex(0xE4EBE3), 0);
    lv_obj_set_style_text_color(input, lv_color_hex(0xC2D5C9), LV_PART_TEXTAREA_PLACEHOLDER);
    lv_obj_set_style_bg_color(input, lv_color_hex(0x12271F), 0);
    keys = lv_buttonmatrix_create(surface);
    lv_obj_set_size(keys, 310, 222); lv_obj_align(keys, LV_ALIGN_TOP_MID, 0, 181);
    lv_obj_set_style_pad_all(keys, 0, 0);
    lv_obj_set_style_pad_row(keys, 3, 0); lv_obj_set_style_pad_column(keys, 3, 0);
    lv_obj_set_style_bg_opa(keys, LV_OPA_TRANSP, 0); lv_obj_set_style_border_width(keys, 0, 0);
    lv_obj_set_style_bg_color(keys, lv_color_hex(0x234538), LV_PART_ITEMS);
    lv_obj_set_style_bg_color(keys, lv_color_hex(0x3D725A), LV_PART_ITEMS | LV_STATE_PRESSED);
    lv_obj_set_style_text_color(keys, lv_color_hex(0xF0F6EF), LV_PART_ITEMS);
    lv_obj_set_style_text_font(keys, &mochi_font_16, LV_PART_ITEMS);
    lv_obj_set_style_pad_all(keys, 0, LV_PART_ITEMS);
    lv_obj_set_style_radius(keys, 8, LV_PART_ITEMS); lv_obj_set_style_shadow_width(keys, 0, LV_PART_ITEMS);
    map_keys(); lv_obj_add_event_cb(keys, key_pressed, LV_EVENT_VALUE_CHANGED, NULL);
    hint = text_label(surface, "", 410, 220);
    lv_obj_set_style_text_font(hint, &mochi_font_14, 0);
    reader = lv_obj_create(surface);
    lv_obj_remove_style_all(reader); lv_obj_set_size(reader, 306, 240);
    lv_obj_align(reader, LV_ALIGN_TOP_MID, 0, 120);
    lv_obj_set_scroll_dir(reader, LV_DIR_VER); lv_obj_set_scrollbar_mode(reader, LV_SCROLLBAR_MODE_AUTO);
    reply_label = text_label(reader, "", 0, 286);
    lv_obj_set_style_text_align(reply_label, LV_TEXT_ALIGN_LEFT, 0);
    lv_obj_set_style_text_line_space(reply_label, 4, 0);
    lv_label_set_long_mode(reply_label, LV_LABEL_LONG_MODE_WRAP);
    again = lv_button_create(surface);
    lv_obj_set_size(again, 220, 44); lv_obj_align(again, LV_ALIGN_TOP_MID, 0, 379);
    lv_obj_set_style_bg_color(again, lv_color_hex(0x234538), 0);
    lv_obj_set_style_shadow_width(again, 0, 0);
    lv_obj_t *caption = text_label(again, "Escribir otro mensaje", 0, 208); lv_obj_center(caption);
    lv_obj_add_event_cb(again, next_message, LV_EVENT_CLICKED, NULL);
    lv_obj_add_flag(surface, LV_OBJ_FLAG_HIDDEN);
}
