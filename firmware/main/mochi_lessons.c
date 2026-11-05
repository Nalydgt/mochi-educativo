/* Small offline lesson runner. NVS contains only the fictional pilot's package,
 * numeric answers and aggregate counters; NVS encryption is not provisioned.
 * Do not store names, recordings, private conversations or protection notices. */
#include "mochi_lessons.h"
#include "mochi.h"
#include "mochi_display.h"
#include "mochi_fonts.h"
#include "mochi_appearance.h"
#include "mochi_education.h"
#include "mochi_education_policy.h"
#include "mochi_lesson_scene.h"
#include "mochi_runtime.h"
#include "esp_random.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "nvs.h"
#include <stdatomic.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define LESSON_MAGIC 0x4d4c5301u
#define MAX_QUESTIONS 5
#define MAX_ANSWERS 40

typedef struct {
    uint8_t a, b, choice, correct;
} answer_t;
typedef struct {
    uint32_t magic;
    char id[37], assignment[37], result[37], title[81], instructions[201];
    uint8_t factors[MAX_QUESTIONS][2];
    uint8_t count, index, attempts, hints, hint_level;
    bool started, completed, synced;
    /* Reclaims the former alignment byte, preserving the installed NVS layout.
     * 0=not sent, 1=detailed, 2=minimal; withdrawal can only reduce detail. */
    uint8_t detail_mode;
    uint32_t elapsed;
    answer_t answers[MAX_ANSWERS];
} lesson_t;
_Static_assert(offsetof(lesson_t, elapsed) == 416, "Preserve previous lesson state offsets");
_Static_assert(sizeof(lesson_t) == 580, "Preserve previous lesson NVS size");

static lesson_t lesson;
static SemaphoreHandle_t guard;
static atomic_bool opened, network_paused;
static atomic_bool intro_open, voice_mode, voice_held;
static atomic_bool question_pending, caption_open;
static atomic_int voice_state = MOCHI_IDLE;
static bool connection_available;
static atomic_int pending_mood = -1;
static lv_obj_t *root, *launch, *launch_hint, *title_label, *question_label, *feedback_label,
    *counter_label, *choices[3], *hint_button, *rest_button, *voice_button,
    *continue_button, *info_button, *scene, *caption_panel, *caption_label,
    *intro_text_panel, *intro_text_label, *help_back_button;
/* Presentation only: dismissing a help sheet never changes a lesson answer. */
static unsigned dismissed_help_revision;
static int option_values[3];
static int64_t running_since;
static unsigned revision, rendered_revision;
static bool last_visible, last_opened, last_intro, last_voice, last_permitted,
    last_voice_permitted, last_english;
static bool last_caption, caption_available, last_captions_enabled;
static bool last_audio_busy, last_reply_available;
static unsigned caption_revision, rendered_caption_revision;
static bool voice_gesture_consumed;
static int last_voice_state;
static int64_t voice_started_at;
static char feedback[220];
/* Up to 700 Unicode characters from the server, transient and never persisted. */
static char voice_caption[2801];
static char *last_reply;
static const char *words(const char *spanish, const char *english);

static bool uuid(const char *s) {
    if (!s || strlen(s) != 36)
        return false;
    for (int i = 0; i < 36; i++) {
        if (i == 8 || i == 13 || i == 18 || i == 23) {
            if (s[i] != '-')
                return false;
        } else if (!((s[i] >= '0' && s[i] <= '9') ||
                     (s[i] >= 'a' && s[i] <= 'f') ||
                     (s[i] >= 'A' && s[i] <= 'F')))
            return false;
    }
    return true;
}

static void new_uuid(char output[37]) {
    uint8_t b[16];
    esp_fill_random(b, sizeof(b));
    b[6] = (b[6] & 15) | 64;
    b[8] = (b[8] & 63) | 128;
    snprintf(output, 37,
             "%02x%02x%02x%02x-%02x%02x-%02x%02x-%02x%02x-%02x%02x%02x%02x%02x%02x",
             b[0], b[1], b[2], b[3], b[4], b[5], b[6], b[7], b[8], b[9],
             b[10], b[11], b[12], b[13], b[14], b[15]);
}

static bool valid(const lesson_t *s) {
    if (s->magic != LESSON_MAGIC || !memchr(s->id, 0, sizeof(s->id)) ||
        !memchr(s->assignment, 0, sizeof(s->assignment)) ||
        !memchr(s->result, 0, sizeof(s->result)) ||
        !memchr(s->title, 0, sizeof(s->title)) ||
        !memchr(s->instructions, 0, sizeof(s->instructions)) ||
        !uuid(s->id) || !uuid(s->assignment) || !uuid(s->result) ||
        !s->count || s->count > MAX_QUESTIONS || s->index > s->count ||
        s->attempts > MAX_ANSWERS || s->hints > 40 || s->hint_level > 3 ||
        s->elapsed > 86400 || (s->synced && !s->completed))
        return false;
    for (unsigned i = 0; i < s->count; i++)
        if (!s->factors[i][0] || s->factors[i][0] > 12 ||
            !s->factors[i][1] || s->factors[i][1] > 12)
            return false;
    unsigned position = 0;
    for (unsigned i = 0; i < s->attempts; i++) {
        const answer_t *a = &s->answers[i];
        if (position >= s->count || a->a != s->factors[position][0] ||
            a->b != s->factors[position][1] || a->choice > 144 ||
            a->correct != (a->choice == a->a * a->b))
            return false;
        if (a->correct)
            position++;
    }
    return position == s->index && s->completed == (s->index == s->count);
}

static bool persist(void) {
    nvs_handle_t n;
    esp_err_t error = nvs_open("mochi_lessons", NVS_READWRITE, &n);
    if (error != ESP_OK)
        return false;
    error = nvs_set_blob(n, "state", &lesson, sizeof(lesson));
    if (error == ESP_OK)
        error = nvs_commit(n);
    nvs_close(n);
    return error == ESP_OK;
}

static void elapsed(void) {
    if (!running_since || lesson.completed)
        return;
    int64_t now = esp_timer_get_time();
    uint32_t seconds = (uint32_t)((now - running_since) / 1000000);
    if (seconds) {
        uint32_t total = lesson.elapsed + seconds;
        lesson.elapsed = total > 86400 ? 86400 : total;
        running_since += (int64_t)seconds * 1000000;
    }
}

static void message(const char *text) {
    snprintf(feedback, sizeof(feedback), "%s", text);
    revision++;
}

static bool store_or_restore(const lesson_t *before) {
    if (persist()) {
        revision++;
        return true;
    }
    lesson = *before;
    message(words("No pude guardar. Descansa y pide ayuda a un adulto.",
                  "I could not save. Take a break and ask an adult for help."));
    return false;
}

static bool start(bool introductory) {
    if (!guard)
        return false;
    if (!mochi_education_policy_practice()) {
        mochi_education_notice(mochi_education_policy_notice(), 5000);
        return false;
    }
    xSemaphoreTake(guard, portMAX_DELAY);
    bool ok = lesson.magic == LESSON_MAGIC;
    if (ok && atomic_load(&opened)) {
        atomic_store(&intro_open, introductory);
        atomic_store(&question_pending, !lesson.completed);
        xSemaphoreGive(guard);
        return true;
    }
    if (ok) {
        lesson_t before = lesson;
        lesson.started = true;
        ok = store_or_restore(&before);
        if (ok) {
            atomic_store(&opened, true);
            atomic_store(&intro_open, introductory);
            atomic_store(&question_pending, !lesson.completed);
            running_since = lesson.completed ? 0 : esp_timer_get_time();
            message(lesson.completed ? words("Ya me has enseñado a agrupar. ¡Gracias!", "You taught me to group. Thank you!")
                                    : lesson.instructions);
        }
    }
    xSemaphoreGive(guard);
    if (ok)
        mochi_display_activity();
    return ok;
}

static void rest(void) {
    if (atomic_exchange(&voice_mode, false) || mochi_runtime_education_narrating())
        mochi_voice_cancel();
    atomic_store(&voice_held, false);
    atomic_store(&intro_open, false);
    atomic_store(&caption_open, false);
    xSemaphoreTake(guard, portMAX_DELAY);
    lesson_t before = lesson;
    elapsed();
    store_or_restore(&before);
    running_since = 0;
    atomic_store(&opened, false);
    memset(voice_caption, 0, sizeof(voice_caption));
    if (last_reply)
        memset(last_reply, 0, 2801);
    last_reply_available = false;
    caption_available = false;
    caption_revision++;
    revision++;
    xSemaphoreGive(guard);
    mochi_education_policy_flush();
    mochi_display_activity();
}

static bool guided(void) {
    return !lesson.completed && lesson.attempts >= MAX_ANSWERS - (lesson.count - lesson.index);
}

static bool answer_internal(int choice, bool spoken, const char *expected_id, int expected_step) {
    if (!guard || choice < 0 || choice > 144 || !mochi_education_policy_practice() ||
        (!spoken && atomic_load(&voice_mode)))
        return false;
    xSemaphoreTake(guard, portMAX_DELAY);
    if (!atomic_load(&opened) || !lesson.magic || lesson.completed ||
        lesson.attempts >= MAX_ANSWERS || (spoken && (!expected_id ||
        strcmp(lesson.id, expected_id) || expected_step < 0 || expected_step != lesson.index))) {
        xSemaphoreGive(guard);
        return false;
    }
    unsigned a = lesson.factors[lesson.index][0], b = lesson.factors[lesson.index][1];
    bool correct = choice == (int)(a * b);
    if (guided() && !correct) {
        message(words("Vamos paso a paso. Toca la respuesta acompañada.", "One step at a time. Tap the guided answer."));
        xSemaphoreGive(guard);
        return false;
    }
    lesson_t before = lesson;
    if (!spoken || !atomic_load(&caption_open))
        caption_available = false;
    elapsed();
    if (guided() && lesson.hints < 40)
        lesson.hints++;
    lesson.answers[lesson.attempts++] = (answer_t){a, b, choice, correct};
    if (correct) {
        lesson.index++;
        lesson.hint_level = 0;
        if (lesson.index == lesson.count) {
            lesson.completed = true;
            atomic_store(&question_pending, false);
            message(words("¡Ahora sé agrupar! Tu progreso está guardado aquí.", "Now I can group! Your progress is saved here."));
        } else {
            atomic_store(&question_pending, true);
            message(words("¡Lo entiendo! ¿Me enseñas con estos grupos nuevos?", "I see! Can you teach me with these new groups?"));
        }
    } else {
        char text[220];
        snprintf(text, sizeof(text),
                 words("Contemos otra vez: %u grupos de %u. Puedes pedir una pista.",
                       "Let's count again: %u groups of %u. You can ask for a hint."), a, b);
        message(text);
    }
    bool ok = store_or_restore(&before);
    if (ok && lesson.completed)
        running_since = 0;
    xSemaphoreGive(guard);
    if (ok) {
        if (!spoken && mochi_voice_busy())
            mochi_voice_cancel();
        mochi_display_activity();
        atomic_store(&pending_mood, correct ? MOCHI_PROUD : MOCHI_CURIOUS);
    }
    return ok;
}
static bool answer(int choice) { return answer_internal(choice, false, NULL, -1); }
bool mochi_lessons_spoken_answer(const char *id, int step, int choice) {
    return answer_internal(choice, true, id, step);
}

static bool hint(void) {
    if (!guard || !mochi_education_policy_practice() || atomic_load(&voice_mode))
        return false;
    xSemaphoreTake(guard, portMAX_DELAY);
    if (!atomic_load(&opened) || !lesson.magic || lesson.completed) {
        xSemaphoreGive(guard);
        return false;
    }
    lesson_t before = lesson;
    caption_available = false;
    elapsed();
    if (lesson.hints < 40)
        lesson.hints++;
    if (lesson.hint_level < 3)
        lesson.hint_level++;
    unsigned a = lesson.factors[lesson.index][0], b = lesson.factors[lesson.index][1];
    char text[220];
    if (lesson.hint_level == 1)
        snprintf(text, sizeof(text), words("Hay %u grupos. Cada uno tiene %u objetos. Cuenta por grupos.",
                                           "There are %u groups, each with %u objects. Count the groups."), a, b);
    else if (lesson.hint_level == 2 && a == 1)
        snprintf(text, sizeof(text), words("Hay un solo grupo de %u. Cuenta los objetos de ese grupo.",
                                           "There is one group of %u. Count the objects in that group."), b);
    else if (lesson.hint_level == 2)
        snprintf(text, sizeof(text), words("Suma %u un total de %u veces. Dos grupos ya son %u.",
                                           "Add %u a total of %u times. Two groups already make %u."), b, a, b * 2);
    else
        snprintf(text, sizeof(text), words("%u grupos de %u son %u. ¿Qué opción muestra el total?",
                                           "%u groups of %u make %u. Which answer shows the total?"), a, b, a * b);
    message(text);
    bool ok = store_or_restore(&before);
    xSemaphoreGive(guard);
    if (ok)
        mochi_display_activity();
    return ok;
}

static const char *json_text(const cJSON *p, const char *key) {
    const cJSON *v = cJSON_GetObjectItemCaseSensitive(p, key);
    return cJSON_IsString(v) ? v->valuestring : "";
}

bool mochi_lessons_offer(const cJSON *package) {
    if (!guard || !cJSON_IsObject(package))
        return false;
    lesson_t incoming = {0};
    const char *id = json_text(package, "id"), *assignment = json_text(package, "assignmentId"),
        *title = json_text(package, "title"), *instructions = json_text(package, "instructions");
    const cJSON *factors = cJSON_GetObjectItemCaseSensitive(package, "factors");
    int count = cJSON_GetArraySize(factors);
    if (!uuid(id) || !uuid(assignment) || strcmp(json_text(package, "kind"), "multiplication") ||
        !title[0] || strlen(title) > 80 || strlen(instructions) > 200 ||
        !cJSON_IsArray(factors) || count < 1 || count > MAX_QUESTIONS)
        return false;
    for (int i = 0; i < count; i++) {
        const cJSON *pair = cJSON_GetArrayItem(factors, i);
        const cJSON *a = cJSON_GetArrayItem(pair, 0), *b = cJSON_GetArrayItem(pair, 1);
        if (!cJSON_IsArray(pair) || cJSON_GetArraySize(pair) != 2 || !cJSON_IsNumber(a) ||
            !cJSON_IsNumber(b) || a->valuedouble != a->valueint || b->valuedouble != b->valueint ||
            a->valueint < 1 || a->valueint > 12 || b->valueint < 1 || b->valueint > 12)
            return false;
        incoming.factors[i][0] = a->valueint;
        incoming.factors[i][1] = b->valueint;
    }
    incoming.magic = LESSON_MAGIC;
    incoming.count = count;
    snprintf(incoming.id, sizeof(incoming.id), "%s", id);
    snprintf(incoming.assignment, sizeof(incoming.assignment), "%s", assignment);
    snprintf(incoming.title, sizeof(incoming.title), "%s", title);
    snprintf(incoming.instructions, sizeof(incoming.instructions), "%s", instructions);
    new_uuid(incoming.result);
    xSemaphoreTake(guard, portMAX_DELAY);
    if (lesson.magic && (!strcmp(lesson.id, incoming.id) || !lesson.synced ||
        atomic_load(&caption_open) || atomic_load(&voice_mode) ||
        (lesson.completed && atomic_load(&opened)))) {
        bool same = !strcmp(lesson.id, incoming.id);
        xSemaphoreGive(guard);
        return same;
    }
    lesson_t before = lesson;
    lesson = incoming;
    bool ok = store_or_restore(&before);
    if (ok) {
        atomic_store(&opened, false);
        atomic_store(&intro_open, false);
        if (atomic_exchange(&voice_mode, false))
            mochi_voice_cancel();
        atomic_store(&voice_held, false);
        atomic_store(&caption_open, false);
        atomic_store(&question_pending, false);
        caption_available = false;
        memset(voice_caption, 0, sizeof(voice_caption));
        if (last_reply)
            memset(last_reply, 0, 2801);
        last_reply_available = false;
        caption_revision++;
        running_since = 0;
        message("Tu docente ha preparado una misión. Puedes hacerla sin internet.");
    }
    xSemaphoreGive(guard);
    return ok;
}

cJSON *mochi_lessons_pending_result(void) {
    if (!guard)
        return NULL;
    xSemaphoreTake(guard, portMAX_DELAY);
    if (!lesson.magic || !lesson.completed || lesson.synced) {
        xSemaphoreGive(guard);
        return NULL;
    }
    bool sharing = mochi_education_policy_share();
    uint8_t next_mode = !sharing || lesson.detail_mode == 2 ? 2 : 1;
    if (lesson.detail_mode != next_mode) {
        lesson_t before = lesson;
        lesson.detail_mode = next_mode;
        if (!store_or_restore(&before)) {
            xSemaphoreGive(guard);
            return NULL;
        }
    }
    bool details = lesson.detail_mode == 1;
    cJSON *body = cJSON_CreateObject(), *answers = cJSON_CreateArray();
    if (!body || !answers) {
        cJSON_Delete(body);
        cJSON_Delete(answers);
        xSemaphoreGive(guard);
        return NULL;
    }
    cJSON_AddStringToObject(body, "resultId", lesson.result);
    cJSON_AddStringToObject(body, "lessonId", lesson.id);
    cJSON_AddStringToObject(body, "assignmentId", lesson.assignment);
    cJSON_AddBoolToObject(body, "completed", true);
    cJSON_AddBoolToObject(body, "detailsShared", details);
    cJSON_AddNumberToObject(body, "completedCount", lesson.count);
    cJSON_AddNumberToObject(body, "attempts", lesson.attempts);
    cJSON_AddNumberToObject(body, "hints", lesson.hints);
    cJSON_AddNumberToObject(body, "elapsedSeconds", lesson.elapsed);
    cJSON_AddItemToObject(body, "answers", answers);
    for (unsigned i = 0; details && i < lesson.attempts; i++) {
        const answer_t *a = &lesson.answers[i];
        cJSON *entry = cJSON_CreateObject();
        if (!entry) {
            cJSON_Delete(body);
            xSemaphoreGive(guard);
            return NULL;
        }
        cJSON_AddNumberToObject(entry, "a", a->a);
        cJSON_AddNumberToObject(entry, "b", a->b);
        cJSON_AddNumberToObject(entry, "choice", a->choice);
        cJSON_AddBoolToObject(entry, "correct", a->correct);
        cJSON_AddItemToArray(answers, entry);
    }
    xSemaphoreGive(guard);
    return body;
}

bool mochi_lessons_acknowledge(const char *result_id) {
    if (!guard || !uuid(result_id))
        return false;
    xSemaphoreTake(guard, portMAX_DELAY);
    bool ok = lesson.magic && lesson.completed && !strcmp(lesson.result, result_id);
    if (ok && !lesson.synced) {
        lesson_t before = lesson;
        lesson.synced = true;
        ok = store_or_restore(&before);
        if (ok)
            message("Progreso enviado. Tu docente podrá revisarlo.");
    }
    xSemaphoreGive(guard);
    return ok;
}

bool mochi_lessons_forget(void) {
    if (!guard)
        return true;
    xSemaphoreTake(guard, portMAX_DELAY);
    nvs_handle_t n;
    esp_err_t error = nvs_open("mochi_lessons", NVS_READWRITE, &n);
    if (error == ESP_OK) {
        error = nvs_erase_key(n, "state");
        if (error == ESP_ERR_NVS_NOT_FOUND)
            error = ESP_OK;
        if (error == ESP_OK)
            error = nvs_commit(n);
        nvs_close(n);
    }
    if (error == ESP_OK) {
        memset(&lesson, 0, sizeof(lesson));
        running_since = 0;
        atomic_store(&opened, false);
        atomic_store(&intro_open, false);
        atomic_store(&voice_mode, false);
        atomic_store(&voice_held, false);
        atomic_store(&caption_open, false);
        atomic_store(&question_pending, false);
        caption_available = false;
        memset(voice_caption, 0, sizeof(voice_caption));
        if (last_reply)
            memset(last_reply, 0, 2801);
        last_reply_available = false;
        caption_revision++;
        revision++;
    }
    xSemaphoreGive(guard);
    return error == ESP_OK;
}

bool mochi_lessons_network_paused(void) { return atomic_load(&network_paused); }
bool mochi_lessons_interacting(void) { return atomic_load(&opened); }
bool mochi_lessons_voice_passthrough(void) { return atomic_load(&voice_mode); }
void mochi_lessons_voice_state(int state) { atomic_store(&voice_state, state); }
bool mochi_lessons_voice_begin(void) {
    if (!guard || !mochi_education_active())
        return false;
    const char *reason = !mochi_education_policy_voice() ? mochi_education_policy_notice() : NULL;
    xSemaphoreTake(guard, portMAX_DELAY);
    if (!atomic_load(&opened)) {
        xSemaphoreGive(guard);
        return false;
    }
    if (!reason && (!connection_available || atomic_load(&network_paused)))
        reason = words("La voz necesita conexión. Tu misión funciona aquí sin internet.",
                       "Voice needs a connection. Your downloaded lesson still works here.");
    if (reason) {
        caption_available = false;
        message(reason);
        xSemaphoreGive(guard);
        return false;
    }
    if (atomic_load(&voice_mode) && atomic_load(&voice_held)) {
        xSemaphoreGive(guard);
        return true;
    }
    voice_started_at = esp_timer_get_time();
    atomic_store(&voice_held, true);
    atomic_store(&voice_mode, true);
    atomic_store(&voice_state, MOCHI_LISTENING);
    atomic_store(&caption_open, false);
    caption_available = false;
    memset(voice_caption, 0, sizeof(voice_caption));
    caption_revision++;
    revision++;
    xSemaphoreGive(guard);
    return true;
}
void mochi_lessons_voice_end(void) {
    atomic_store(&voice_held, false);
    /* Failed setup has neither recording nor a busy audio owner. A genuine
     * release keeps its reply/caption alive while the owner finishes the turn. */
    if (!mochi_voice_recording() && !mochi_voice_busy())
        atomic_store(&voice_mode, false);
}
bool mochi_lessons_voice_context(char id[37], int *step, int *a, int *b) {
    if (!guard || !id || !step || !a || !b || !mochi_education_active() || !mochi_education_policy_practice())
        return false;
    xSemaphoreTake(guard, portMAX_DELAY);
    bool ok = lesson.magic && !lesson.completed && atomic_load(&opened) && !atomic_load(&intro_open);
    if (ok) {
        snprintf(id, 37, "%s", lesson.id);
        *step = lesson.index;
        *a = lesson.factors[lesson.index][0];
        *b = lesson.factors[lesson.index][1];
    }
    xSemaphoreGive(guard);
    return ok;
}
bool mochi_lessons_pending_question(char id[37], int *step) {
    if (!atomic_load(&question_pending) || atomic_load(&voice_mode) || atomic_load(&caption_open) ||
        !mochi_education_policy_voice() || mochi_education_policy_text_first())
        return false;
    int a,b;
    return mochi_lessons_voice_context(id, step, &a, &b);
}
void mochi_lessons_question_announced(const char *id, int step) {
    if (!guard || !id)
        return;
    xSemaphoreTake(guard, portMAX_DELAY);
    if (lesson.magic && !strcmp(lesson.id, id) && step == lesson.index)
        atomic_store(&question_pending, false);
    xSemaphoreGive(guard);
}
void mochi_lessons_voice_caption(const char *text) {
    if (!guard || !text)
        return;
    xSemaphoreTake(guard, portMAX_DELAY);
    if (atomic_load(&opened)) {
        snprintf(voice_caption, sizeof(voice_caption), "%s", text);
        caption_available = voice_caption[0] != 0;
        if (caption_available && atomic_load(&voice_mode) && last_reply) {
            snprintf(last_reply, 2801, "%s", text);
            last_reply_available = true;
        }
        /* Ordinary subtitles follow the audio without adding a confirmation
         * step. Text-first mode alone automatically keeps a reading view. */
        if (caption_available && mochi_education_policy_text_first() && mochi_education_policy_captions())
            atomic_store(&caption_open, true);
        caption_revision++;
        revision++;
    }
    xSemaphoreGive(guard);
}
void mochi_lessons_connection(bool available) {
    if (!guard)
        return;
    xSemaphoreTake(guard, portMAX_DELAY);
    if (connection_available != available) {
        connection_available = available;
        revision++;
    }
    xSemaphoreGive(guard);
}

static const char *words(const char *spanish, const char *english) {
    return mochi_education_policy_english() ? english : spanish;
}
static bool continue_lesson(void) {
    if (!guard || !mochi_education_policy_practice() || atomic_load(&voice_mode))
        return false;
    xSemaphoreTake(guard, portMAX_DELAY);
    bool ok = lesson.magic == LESSON_MAGIC && atomic_load(&opened) && !lesson.completed;
    if (ok) {
        atomic_store(&intro_open, false);
        atomic_store(&question_pending, true);
        if (!running_since)
            running_since = esp_timer_get_time();
        message(words("¿Cuántos hay en total? Enséñame contando.", "How many are there? Teach me by counting."));
    }
    xSemaphoreGive(guard);
    return ok;
}
static void clicked(lv_event_t *event) {
    intptr_t action = (intptr_t)lv_event_get_user_data(event);
    if (action == 1) {
        bool first;
        xSemaphoreTake(guard, portMAX_DELAY);
        first = !lesson.started && !lesson.completed;
        xSemaphoreGive(guard);
        start(first);
    } else if (action == 2) {
        if (atomic_load(&voice_mode) || atomic_load(&caption_open)) {
            mochi_voice_cancel();
            atomic_store(&voice_mode, false);
            atomic_store(&voice_held, false);
            atomic_store(&caption_open, false);
            xSemaphoreTake(guard, portMAX_DELAY);
            caption_available = false;
            memset(voice_caption, 0, sizeof(voice_caption));
            caption_revision++;
            message(lesson.completed ? words("Tu progreso sigue guardado.", "Your progress is saved.") :
                    words("¿Cuántos hay en total? Enséñame contando.", "How many are there? Teach me by counting."));
            xSemaphoreGive(guard);
        } else
            rest();
    } else if (action == 3)
        hint();
    else if (action == 4)
        continue_lesson();
    else if (action == 5 && !atomic_load(&voice_mode)) {
        bool stop_audio = false;
        xSemaphoreTake(guard, portMAX_DELAY);
        if (atomic_load(&caption_open)) {
            atomic_store(&caption_open, false);
            atomic_store(&intro_open, !lesson.completed);
        } else if (last_reply_available && last_reply && mochi_education_policy_captions()) {
            snprintf(voice_caption, sizeof(voice_caption), "%s", last_reply);
            caption_available = true;
            atomic_store(&caption_open, true);
            caption_revision++;
            revision++;
            stop_audio = true;
        } else if (!lesson.completed)
            atomic_store(&intro_open, true);
        xSemaphoreGive(guard);
        if (stop_audio && mochi_voice_busy())
            mochi_voice_cancel();
    }
    else if (action >= 10 && action < 13)
        answer(option_values[action - 10]);
}
static void voice_event(lv_event_t *event) {
    lv_event_code_t code = lv_event_get_code(event);
    if (code == LV_EVENT_PRESSED) {
        voice_gesture_consumed = false;
        mochi_display_activity();
    }
    if (code == LV_EVENT_LONG_PRESSED && !atomic_load(&voice_mode)) {
        voice_gesture_consumed = true;
        if (mochi_voice_busy()) {
            xSemaphoreTake(guard, portMAX_DELAY);
            caption_available = false;
            message(words("Espera a que termine. Después vuelve a mantener para responder.",
                          "Wait until it finishes, then hold again to answer."));
            xSemaphoreGive(guard);
            return;
        }
        if (!mochi_lessons_voice_begin())
            return;
        mochi_voice_start();
        if (!mochi_voice_recording() && !mochi_voice_busy()) {
            mochi_lessons_voice_end();
            xSemaphoreTake(guard, portMAX_DELAY);
            message(words("El micrófono está desactivado o no está listo. Pide ayuda a un adulto.",
                          "The microphone is off or not ready. Ask an adult for help."));
            xSemaphoreGive(guard);
        }
    }
    if ((code == LV_EVENT_RELEASED || code == LV_EVENT_PRESS_LOST) && atomic_exchange(&voice_held, false)) {
        mochi_voice_stop();
        mochi_lessons_voice_end();
    }
    if (code == LV_EVENT_CLICKED && !voice_gesture_consumed && atomic_load(&voice_mode)) {
        mochi_voice_cancel();
        atomic_store(&voice_mode, false);
        atomic_store(&voice_held, false);
    }
}
static void close_help(lv_event_t *event) {
    (void)event;
    xSemaphoreTake(guard, portMAX_DELAY);
    dismissed_help_revision = revision;
    rendered_revision = revision - 1;
    xSemaphoreGive(guard);
    mochi_display_activity();
}
static bool routine_feedback(void) {
    return !feedback[0] || !strcmp(feedback, lesson.instructions) ||
        !strcmp(feedback, words("¿Cuántos hay en total? Enséñame contando.", "How many are there? Teach me by counting.")) ||
        !strcmp(feedback, words("¡Lo entiendo! ¿Me enseñas con estos grupos nuevos?", "I see! Can you teach me with these new groups?")) ||
        !strcmp(feedback, "Tu docente ha preparado una misión. Puedes hacerla sin internet.");
}
static lv_obj_t *label(lv_obj_t *parent, int y, int width, int height) {
    lv_obj_t *o = lv_label_create(parent);
    lv_obj_set_size(o, width, height);
    lv_obj_align(o, LV_ALIGN_TOP_MID, 0, y);
    lv_obj_set_style_text_font(o, &mochi_font_14, 0);
    lv_obj_set_style_text_color(o, lv_color_hex(0xD8E0DA), 0);
    lv_obj_set_style_text_align(o, LV_TEXT_ALIGN_CENTER, 0);
    lv_label_set_long_mode(o, LV_LABEL_LONG_MODE_WRAP);
    lv_label_set_text(o, "");
    lv_obj_remove_flag(o, LV_OBJ_FLAG_CLICKABLE);
    return o;
}
static lv_obj_t *button(lv_obj_t *parent, const char *text, int x, int y, int width,
                        int height, intptr_t action) {
    lv_obj_t *o = lv_button_create(parent);
    lv_obj_set_size(o, width, height);
    lv_obj_align(o, LV_ALIGN_TOP_MID, x, y);
    lv_obj_set_style_bg_color(o, lv_color_hex(0x18362E), 0);
    lv_obj_set_style_bg_color(o, lv_color_hex(0x31594A), LV_STATE_PRESSED);
    lv_obj_set_style_radius(o, 12, 0);
    lv_obj_set_style_shadow_width(o, 0, 0);
    lv_obj_set_style_border_width(o, 1, 0);
    lv_obj_set_style_border_color(o, lv_color_hex(0x5F8D77), 0);
    lv_obj_set_style_pad_all(o, 0, 0);
    lv_obj_add_event_cb(o, clicked, LV_EVENT_CLICKED, (void *)action);
    lv_obj_t *caption = lv_label_create(o);
    lv_obj_set_style_text_font(caption, &mochi_font_16, 0);
    lv_obj_set_style_text_color(caption, lv_color_hex(0xEDF5EB), 0);
    lv_label_set_text(caption, text);
    lv_obj_center(caption);
    return o;
}
static void show(lv_obj_t *o, bool visible) {
    if (visible)
        lv_obj_remove_flag(o, LV_OBJ_FLAG_HIDDEN);
    else
        lv_obj_add_flag(o, LV_OBJ_FLAG_HIDDEN);
}
void mochi_lessons_create(lv_obj_t *parent) {
    guard = xSemaphoreCreateMutex();
    if (!guard)
        return;
    last_reply = heap_caps_calloc(2801, 1, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    nvs_handle_t n;
    if (nvs_open("mochi_lessons", NVS_READONLY, &n) == ESP_OK) {
        size_t size = sizeof(lesson);
        if (nvs_get_blob(n, "state", &lesson, &size) != ESP_OK ||
            size != sizeof(lesson) || !valid(&lesson))
            memset(&lesson, 0, sizeof(lesson));
        nvs_close(n);
    }
    root = lv_obj_create(parent);
    lv_obj_remove_style_all(root);
    lv_obj_set_size(root, 466, 466);
    lv_obj_remove_flag(root, LV_OBJ_FLAG_CLICKABLE | LV_OBJ_FLAG_SCROLLABLE);
    /* Mask the character during work, while leaving the real battery and
     * adult settings gear in their established top safe area. */
    lv_obj_t *backdrop = lv_obj_create(root);
    lv_obj_remove_style_all(backdrop);
    lv_obj_set_pos(backdrop, 0, 110);
    lv_obj_set_size(backdrop, 466, 356);
    lv_obj_set_style_bg_color(backdrop, lv_color_black(), 0);
    lv_obj_set_style_bg_opa(backdrop, LV_OPA_COVER, 0);
    lv_obj_remove_flag(backdrop, LV_OBJ_FLAG_CLICKABLE | LV_OBJ_FLAG_SCROLLABLE);
    launch = button(parent, "Nuestro jardín", 0, 330, 278, 76, 1);
    lv_obj_set_style_radius(launch, 22, 0);
    lv_obj_set_style_bg_color(launch, lv_color_hex(0x173B2E), 0);
    lv_obj_set_style_border_color(launch, lv_color_hex(0x6CA888), 0);
    lv_obj_t *launch_caption = lv_obj_get_child(launch, 0);
    lv_obj_set_width(launch_caption, 171);
    lv_obj_align(launch_caption, LV_ALIGN_CENTER, 35, -10);
    lv_obj_set_style_text_color(launch_caption, lv_color_hex(0xF9EED3), 0);
    launch_hint = lv_label_create(launch);
    lv_obj_set_width(launch_hint, 171);
    lv_obj_set_style_text_font(launch_hint, &mochi_font_14, 0);
    lv_obj_set_style_text_color(launch_hint, lv_color_hex(0xBDD6BF), 0);
    lv_label_set_text(launch_hint, "Vamos juntos");
    lv_obj_align(launch_hint, LV_ALIGN_CENTER, 35, 12);
    mochi_lesson_scene_decorate_launcher(launch);
    title_label = label(root, 124, 286, 20);
    lv_label_set_long_mode(title_label, LV_LABEL_LONG_MODE_DOTS);
    lv_obj_set_style_text_color(title_label, lv_color_hex(0xAABCB0), 0);
    question_label = label(root, 147, 318, 26);
    lv_obj_set_style_text_font(question_label, &mochi_font_20, 0);
    scene = mochi_lesson_scene_create(root, 187);
    counter_label = label(root, 124, 286, 20);
    lv_obj_set_style_text_color(counter_label, lv_color_hex(0xAABCB0), 0);
    feedback_label = label(root, 307, 314, 34);
    caption_panel = lv_obj_create(root);
    lv_obj_remove_style_all(caption_panel);
    lv_obj_set_size(caption_panel, 314, 160);
    lv_obj_align(caption_panel, LV_ALIGN_TOP_MID, 0, 174);
    lv_obj_set_style_bg_color(caption_panel, lv_color_black(), 0);
    lv_obj_set_style_bg_opa(caption_panel, LV_OPA_COVER, 0);
    lv_obj_set_style_pad_left(caption_panel, 5, 0);
    lv_obj_set_style_pad_right(caption_panel, 10, 0);
    lv_obj_set_style_pad_top(caption_panel, 2, 0);
    lv_obj_set_style_bg_color(caption_panel, lv_color_hex(0x60836E), LV_PART_SCROLLBAR);
    lv_obj_set_style_width(caption_panel, 3, LV_PART_SCROLLBAR);
    lv_obj_set_scroll_dir(caption_panel, LV_DIR_VER);
    lv_obj_set_scrollbar_mode(caption_panel, LV_SCROLLBAR_MODE_AUTO);
    caption_label = lv_label_create(caption_panel);
    lv_obj_set_width(caption_label, 292);
    lv_label_set_long_mode(caption_label, LV_LABEL_LONG_MODE_WRAP);
    lv_obj_set_style_text_font(caption_label, &mochi_font_16, 0);
    lv_obj_set_style_text_color(caption_label, lv_color_hex(0xE4EBE3), 0);
    lv_obj_set_style_text_line_space(caption_label, 4, 0);
    lv_label_set_text(caption_label, "");
    lv_obj_remove_flag(caption_label, LV_OBJ_FLAG_CLICKABLE);
    show(caption_panel, false);
    intro_text_panel = lv_obj_create(root);
    lv_obj_remove_style_all(intro_text_panel);
    lv_obj_set_size(intro_text_panel, 314, 84);
    lv_obj_align(intro_text_panel, LV_ALIGN_TOP_MID, 0, 254);
    lv_obj_set_scroll_dir(intro_text_panel, LV_DIR_VER);
    lv_obj_set_scrollbar_mode(intro_text_panel, LV_SCROLLBAR_MODE_AUTO);
    lv_obj_set_style_bg_color(intro_text_panel, lv_color_hex(0x60836E), LV_PART_SCROLLBAR);
    lv_obj_set_style_width(intro_text_panel, 3, LV_PART_SCROLLBAR);
    intro_text_label = lv_label_create(intro_text_panel);
    lv_obj_set_width(intro_text_label, 300);
    lv_label_set_long_mode(intro_text_label, LV_LABEL_LONG_MODE_WRAP);
    lv_obj_set_style_text_font(intro_text_label, &mochi_font_16, 0);
    lv_obj_set_style_text_color(intro_text_label, lv_color_hex(0xE4EBE3), 0);
    lv_obj_set_style_text_line_space(intro_text_label, 3, 0);
    lv_label_set_text(intro_text_label, "");
    lv_obj_remove_flag(intro_text_label, LV_OBJ_FLAG_CLICKABLE);
    show(intro_text_panel, false);
    for (int i = 0; i < 3; i++) {
        choices[i] = button(root, "", (i - 1) * 88, 334, 78, 48, 10 + i);
        lv_obj_set_style_text_font(lv_obj_get_child(choices[i], 0), &mochi_font_20, 0);
        const uint32_t fills[] = {0xEDCAA1, 0xADD8C2, 0xACD2DF};
        lv_obj_set_style_bg_color(choices[i], lv_color_hex(fills[i]), 0);
        lv_obj_set_style_bg_color(choices[i], lv_color_hex(0x88B8A3), LV_STATE_PRESSED);
        lv_obj_set_style_border_width(choices[i], 0, 0);
        lv_obj_set_style_text_color(lv_obj_get_child(choices[i], 0), lv_color_hex(0x193B32), 0);
    }
    hint_button = button(root, "Pista", -55, 394, 100, 44, 3);
    rest_button = button(root, "Descansar", 55, 394, 100, 44, 2);
    lv_obj_set_style_text_font(lv_obj_get_child(hint_button, 0), &mochi_font_16, 0);
    lv_obj_set_style_text_font(lv_obj_get_child(rest_button, 0), &mochi_font_16, 0);
    continue_button = button(root, "Empezar", 0, 334, 220, 48, 4);
    lv_obj_set_style_bg_color(continue_button, lv_color_hex(0xF4CD76), 0);
    lv_obj_set_style_bg_color(continue_button, lv_color_hex(0xD8B461), LV_STATE_PRESSED);
    lv_obj_set_style_border_width(continue_button, 0, 0);
    lv_obj_set_style_text_color(lv_obj_get_child(continue_button, 0), lv_color_hex(0x193B32), 0);
    help_back_button = button(root, "Volver al reto", 0, 334, 220, 48, 0);
    lv_obj_set_style_bg_color(help_back_button, lv_color_hex(0xF4CD76), 0);
    lv_obj_set_style_bg_color(help_back_button, lv_color_hex(0xD8B461), LV_STATE_PRESSED);
    lv_obj_set_style_border_width(help_back_button, 0, 0);
    lv_obj_set_style_text_color(lv_obj_get_child(help_back_button, 0), lv_color_hex(0x193B32), 0);
    lv_obj_add_event_cb(help_back_button, close_help, LV_EVENT_CLICKED, NULL);
    show(help_back_button, false);
    lv_obj_add_event_cb(scene, clicked, LV_EVENT_CLICKED, (void *)4);
    info_button = button(root, "Misión", -103, 74, 96, 44, 5);
    lv_obj_set_style_text_font(lv_obj_get_child(info_button, 0), &mochi_font_16, 0);
    lv_obj_set_style_bg_color(info_button, lv_color_hex(0x14231E), 0);
    voice_button = button(root, "Hablar", 24, 74, 96, 44, 0);
    lv_obj_set_style_text_font(lv_obj_get_child(voice_button, 0), &mochi_font_16, 0);
    lv_obj_set_style_bg_color(voice_button, lv_color_hex(0x14231E), 0);
    lv_obj_add_event_cb(voice_button, voice_event, LV_EVENT_ALL, NULL);
    show(continue_button, false);
    show(root, false);
    show(launch, false);
    revision = 1;
}
void mochi_lessons_tick(bool visible) {
    if (!guard || !root)
        return;
    int64_t now = esp_timer_get_time();
    bool permitted = mochi_education_policy_practice();
    bool voice_permitted = mochi_education_policy_voice();
    bool english = mochi_education_policy_english();
    bool audio_busy = mochi_voice_busy();
    bool voice = atomic_load(&voice_mode);
    xSemaphoreTake(guard, portMAX_DELAY);
    int64_t voice_began = voice_started_at;
    xSemaphoreGive(guard);
    if (voice && (!mochi_education_policy_voice() || !visible)) {
        mochi_voice_cancel();
        atomic_store(&voice_mode, false);
        atomic_store(&voice_held, false);
        voice = false;
    }
    if (voice && !atomic_load(&voice_held) && !mochi_voice_busy() &&
        !mochi_voice_recording() && now - voice_began > 1200000) {
        atomic_store(&voice_mode, false);
        voice = false;
    }
    int mood = atomic_exchange(&pending_mood, -1);
    if (visible && mood >= 0)
        mochi_set_state((mochi_state_t)mood, 2000);
    mochi_appearance_t appearance;
    mochi_appearance_get(&appearance);
    xSemaphoreTake(guard, portMAX_DELAY);
    bool is_open = atomic_load(&opened);
    bool captions_enabled = mochi_education_policy_captions() || !connection_available || atomic_load(&network_paused);
    if (!captions_enabled && last_captions_enabled) {
        atomic_store(&caption_open, false);
        caption_available = false;
        last_reply_available = false;
        memset(voice_caption, 0, sizeof(voice_caption));
        if (last_reply)
            memset(last_reply, 0, 2801);
        caption_revision++;
    }
    bool caption_view = atomic_load(&caption_open) && captions_enabled;
    bool intro = atomic_load(&intro_open) && !lesson.completed;
    int speaking_state = atomic_load(&voice_state);
    if ((!visible || !permitted || intro) && last_visible && is_open && running_since) {
        lesson_t before = lesson;
        elapsed();
        store_or_restore(&before);
        running_since = 0;
    } else if (visible && permitted && !intro && !running_since && is_open && !lesson.completed)
        running_since = now;
    bool ready = visible && lesson.magic == LESSON_MAGIC;
    show(launch, ready && !is_open);
    show(root, ready && is_open);
    mochi_lesson_scene_tick(now, appearance.motion, ready && is_open && permitted &&
                            !lv_obj_has_flag(scene, LV_OBJ_FLAG_HIDDEN));
    if (rendered_revision == revision && last_visible == visible && last_opened == is_open &&
        last_intro == intro && last_voice == voice && last_permitted == permitted &&
        last_voice_state == speaking_state && last_voice_permitted == voice_permitted && last_english == english &&
        last_audio_busy == audio_busy) {
        if (last_caption == caption_view && last_captions_enabled == captions_enabled &&
            rendered_caption_revision == caption_revision) {
            xSemaphoreGive(guard);
            return;
        }
    }
    rendered_revision = revision;
    last_visible = visible;
    last_opened = is_open;
    last_intro = intro;
    last_voice = voice;
    last_permitted = permitted;
    last_voice_permitted = voice_permitted;
    last_english = english;
    last_audio_busy = audio_busy;
    last_caption = caption_view;
    last_captions_enabled = captions_enabled;
    last_voice_state = speaking_state;
    if (!ready) {
        xSemaphoreGive(guard);
        return;
    }
    lv_label_set_text(lv_obj_get_child(launch, 0), english ? "Mochi's garden" : "Nuestro jardín");
    lv_label_set_text(launch_hint, lesson.completed ? (english ? "We did it together" : "¡Lo hicimos juntos!") :
                      lesson.started ? (english ? "Let's keep exploring" : "Seguimos explorando") :
                      (english ? "Your lesson is here" : "Tu misión está aquí"));
    if (!is_open) {
        xSemaphoreGive(guard);
        return;
    }
    lv_label_set_text(title_label, lesson.title);
    show(title_label, false);
    lv_obj_set_height(feedback_label, 34);
    lv_obj_align(feedback_label, LV_ALIGN_TOP_MID, 0, 307);
    lv_obj_set_style_text_font(feedback_label, &mochi_font_16, 0);
    show(counter_label, false);
    show(feedback_label, false);
    show(caption_panel, false);
    show(intro_text_panel, false);
    show(help_back_button, false);
    lv_obj_align(rest_button, LV_ALIGN_TOP_MID, 55, 394);
    lv_obj_set_width(rest_button, 100);
    show(continue_button, intro && permitted && !voice && !caption_view);
    show(scene, permitted);
    lv_obj_set_height(scene, 132);
    if (intro && permitted && !voice && !caption_view)
        lv_obj_add_flag(scene, LV_OBJ_FLAG_CLICKABLE);
    else
        lv_obj_remove_flag(scene, LV_OBJ_FLAG_CLICKABLE);
    show(hint_button, !intro && !lesson.completed && permitted && !voice && !caption_view);
    show(voice_button, permitted);
    show(info_button, permitted && !voice && (!lesson.completed || last_reply_available));
    if (voice_permitted)
        lv_obj_remove_state(voice_button, LV_STATE_DISABLED);
    else
        lv_obj_add_state(voice_button, LV_STATE_DISABLED);
    for (int i = 0; i < 3; i++)
        show(choices[i], !intro && !lesson.completed && permitted && !voice && !caption_view);
    lv_label_set_text(lv_obj_get_child(hint_button, 0), english ? "Hint" : "Pista");
    lv_label_set_text(lv_obj_get_child(continue_button, 0), english ? "Start learning" : "Empezar");
    lv_label_set_text(lv_obj_get_child(voice_button, 0), voice ? (english ? "Stop" : "Parar") :
                      !voice_permitted ? (english ? "No voice" : "Sin voz") :
                      (english ? "Speak" : "Hablar"));
    lv_label_set_text(lv_obj_get_child(info_button, 0), caption_view ?
                      (english ? "Back" : "Volver") :
                      last_reply_available && captions_enabled ? (english ? "Read" : "Leer") :
                      (english ? "Lesson" : "Misión"));
    lv_label_set_text(lv_obj_get_child(rest_button, 0), caption_view ? (english ? "Continue" : "Seguir") :
                      voice ? (english ? "Back" : "Volver") :
                      lesson.completed ? (english ? "Back" : "Volver") : (english ? "Rest" : "Descansar"));
    if (!permitted) {
        show(feedback_label, true);
        lv_label_set_text(question_label, english ? "A moment to rest" : "Un momento de descanso");
        lv_label_set_text(counter_label, english ? "Your lesson is saved" : "Tu misión sigue guardada");
        lv_obj_set_height(feedback_label, 110);
        lv_obj_align(feedback_label, LV_ALIGN_TOP_MID, 0, 182);
        lv_obj_set_style_text_font(feedback_label, &mochi_font_16, 0);
        lv_label_set_text(feedback_label, mochi_education_policy_notice());
        lv_obj_align(rest_button, LV_ALIGN_TOP_MID, 0, 352);
        lv_obj_set_width(rest_button, 220);
    } else if (voice || caption_view) {
        bool listening = atomic_load(&voice_held) || speaking_state == MOCHI_LISTENING;
        bool speaking = speaking_state == MOCHI_SPEAKING;
        lv_label_set_text(question_label, !voice && caption_view ? (english ? "Mochi's reply" : "Mochi te cuenta") :
                          listening ? (english ? "I am listening" : "Te escucho") :
                          speaking ? (english ? "Mochi explains" : "Mochi te cuenta") :
                          (english ? "Thinking together" : "Pensamos juntos"));
        lv_label_set_text(counter_label, english ? "Connected voice" : "Voz conectada");
        lv_label_set_text(feedback_label, listening ? (english ? "Release when you finish speaking." : "Suelta cuando termines de hablar.") :
                          (english ? "Your lesson is still saved here." : "Tu misión sigue guardada aquí."));
        show(feedback_label, true);
        lv_obj_set_height(scene, 100);
        lv_obj_set_height(feedback_label, 42);
        lv_obj_align(feedback_label, LV_ALIGN_TOP_MID, 0, 300);
        mochi_lesson_scene_set(MOCHI_SCENE_VOICE, 0, 0, 0, lesson.index, lesson.count,
                              listening || speaking || mochi_voice_busy());
        if (caption_available && captions_enabled && (audio_busy || caption_view)) {
            show(scene, false);
            show(feedback_label, false);
            show(counter_label, false);
            show(caption_panel, true);
            lv_obj_set_height(caption_panel, 148);
            lv_obj_align(caption_panel, LV_ALIGN_TOP_MID, 0, 187);
        }
        lv_obj_align(rest_button, LV_ALIGN_TOP_MID, 0, 352);
        lv_obj_set_width(rest_button, 220);
    } else if (intro) {
        lv_label_set_text(question_label, english ? "Mochi's little garden" : "El jardín de Mochi");
        lv_label_set_text(counter_label, english ? "At your pace. You can take a break." : "Sin prisa. Puedes descansar.");
        show(counter_label, false);
        lv_obj_set_height(scene, 76);
        show(intro_text_panel, true);
        lv_obj_set_height(intro_text_panel, 52);
        lv_obj_align(intro_text_panel, LV_ALIGN_TOP_MID, 0, 274);
        lv_label_set_text_fmt(intro_text_label, english ? "%s\n%u of %u · %s\n\nHold Speak to answer by voice.\n\n%s" :
                             "%s\n%u de %u · %s\n\nMantén Hablar para responder con voz.\n\n%s",
                             lesson.title, lesson.index + 1, lesson.count,
                             connection_available ? (english ? "Saved here" : "Guardado aquí") :
                             (english ? "Offline lesson" : "Sin conexión"), lesson.instructions);
        mochi_lesson_scene_set(MOCHI_SCENE_HUB, 0, 0, 0, lesson.index, lesson.count, false);
        lv_obj_align(rest_button, LV_ALIGN_TOP_MID, 0, 394);
        lv_obj_set_width(rest_button, 140);
    } else if (lesson.completed) {
        show(feedback_label, true);
        lv_obj_set_height(scene, 100);
        lv_obj_set_height(feedback_label, 42);
        lv_obj_align(feedback_label, LV_ALIGN_TOP_MID, 0, 300);
        lv_label_set_text(question_label, english ? "You taught me to group!" : "¡Ya sé hacer grupos!");
        lv_label_set_text(counter_label, lesson.synced ? (english ? "Progress synchronized" : "Progreso sincronizado") :
                          atomic_load(&network_paused) ? (english ? "Network test · Waiting to send" : "Prueba sin red · Envío pendiente") :
                          !mochi_education_policy_share() ? (english ? "No answer detail · Waiting to send" : "Sin detalle · Envío pendiente") :
                          (english ? "Saved here · Waiting to send" : "Guardado aquí · Envío pendiente"));
        lv_label_set_text(feedback_label, lesson.synced ? (english ? "Your teacher can now review your practice." : "Tu docente ya puede revisar la práctica.") :
                          (english ? "We will send your progress when connected." : "Enviaremos el progreso cuando haya conexión."));
        mochi_lesson_scene_set(MOCHI_SCENE_COMPLETE, 0, 0, 0, lesson.index, lesson.count, false);
        lv_obj_align(rest_button, LV_ALIGN_TOP_MID, 0, 352);
        lv_obj_set_width(rest_button, 220);
    } else {
        unsigned a = lesson.factors[lesson.index][0], b = lesson.factors[lesson.index][1];
        unsigned product = a * b;
        unsigned theme = lesson.index % 3;
        const char *const containers_es[] = {a == 1 ? "cesta" : "cestas", a == 1 ? "estanque" : "estanques", a == 1 ? "caja" : "cajas"};
        const char *const objects_es[] = {b == 1 ? "manzana" : "manzanas", b == 1 ? "pez" : "peces", b == 1 ? "coche" : "coches"};
        const char *const containers_en[] = {a == 1 ? "basket" : "baskets", a == 1 ? "pond" : "ponds", a == 1 ? "box" : "boxes"};
        const char *const objects_en[] = {b == 1 ? "apple" : "apples", "fish", b == 1 ? "car" : "cars"};
        lv_label_set_text_fmt(question_label, english ? "%u %s with %u %s" : "%u %s con %u %s", a,
                             english ? containers_en[theme] : containers_es[theme], b,
                             english ? objects_en[theme] : objects_es[theme]);
        lv_label_set_text_fmt(counter_label, english ? "%u of %u · %s" : "%u de %u · %s", lesson.index + 1, lesson.count,
                              atomic_load(&network_paused) ? (english ? "Network test" : "Prueba sin red") :
                              connection_available ? (english ? "Saved here" : "Guardado aquí") :
                              (english ? "Offline lesson" : "Misión sin conexión"));
        lv_label_set_text(feedback_label, feedback[0] && strcmp(feedback, lesson.instructions) ? feedback :
                          (english ? "How many are there? Teach me by counting." : "¿Cuántos hay en total? Enséñame contando."));
        int correct_slot = (lesson.index + 1) % 3;
        int wrong1 = product + b <= 144 ? product + b : product - b;
        int wrong2 = product >= b ? product - b : product + 1;
        if (wrong2 == wrong1 || wrong2 == (int)product)
            wrong2 = product > 1 ? product - 1 : product + 1;
        option_values[correct_slot] = product;
        option_values[(correct_slot + 1) % 3] = wrong1;
        option_values[(correct_slot + 2) % 3] = wrong2;
        if (guided()) {
            lv_label_set_text_fmt(feedback_label, english ? "Together: %u groups of %u make %u. Tap the total." :
                                 "Juntos: %u grupos de %u son %u. Toca el total.", a, b, product);
            for (int i = 0; i < 3; i++)
                show(choices[i], i == correct_slot);
        }
        for (int i = 0; i < 3; i++)
            lv_label_set_text_fmt(lv_obj_get_child(choices[i], 0), "%d", option_values[i]);
        mochi_lesson_scene_set(MOCHI_SCENE_GROUPS, a, b, lesson.hint_level, lesson.index, lesson.count, false);
        bool help_sheet = (guided() || !routine_feedback()) && dismissed_help_revision != revision && !audio_busy;
        if (help_sheet) {
            show(scene, false);
            show(intro_text_panel, true);
            lv_obj_set_height(intro_text_panel, 132);
            lv_obj_align(intro_text_panel, LV_ALIGN_TOP_MID, 0, 187);
            lv_label_set_text(intro_text_label, lv_label_get_text(feedback_label));
            show(help_back_button, true);
            lv_label_set_text(lv_obj_get_child(help_back_button, 0), english ? "Back to the task" : "Volver al reto");
            for (int i = 0; i < 3; i++)
                show(choices[i], false);
        }
        if (caption_available && captions_enabled && audio_busy) {
            show(scene, false);
            show(counter_label, false);
            show(feedback_label, false);
            show(caption_panel, true);
            lv_obj_set_height(caption_panel, 132);
            lv_obj_align(caption_panel, LV_ALIGN_TOP_MID, 0, 187);
        }
    }
    if (rendered_caption_revision != caption_revision) {
        lv_label_set_text(caption_label, voice_caption);
        lv_obj_scroll_to_y(caption_panel, 0, LV_ANIM_OFF);
        rendered_caption_revision = caption_revision;
    }
    mochi_lesson_scene_tick(now, appearance.motion, permitted &&
                            !lv_obj_has_flag(scene, LV_OBJ_FLAG_HIDDEN));
    xSemaphoreGive(guard);
}

bool mochi_lessons_console(const char *line) {
    if (!strcmp(line, "@lesson-continue")) {
        printf("@mochi_lesson_continue accepted=%d\n", continue_lesson());
        return true;
    }
    if (!strcmp(line, "@lesson-status")) {
        if (!guard) {
            printf("@mochi_lesson ready=0\n");
            return true;
        }
        xSemaphoreTake(guard, portMAX_DELAY);
        unsigned i = lesson.index < lesson.count ? lesson.index : 0;
        printf("@mochi_lesson ready=%d open=%d completed=%d queued=%d synced=%d question=%u count=%u attempts=%u hints=%u a=%u b=%u simulation=%d intro=%d voice_mode=%d\n",
               lesson.magic == LESSON_MAGIC, atomic_load(&opened), lesson.completed,
               lesson.completed && !lesson.synced, lesson.synced,
               lesson.magic ? lesson.index + 1 : 0, lesson.count, lesson.attempts, lesson.hints,
               lesson.magic && !lesson.completed ? lesson.factors[i][0] : 0,
               lesson.magic && !lesson.completed ? lesson.factors[i][1] : 0,
               atomic_load(&network_paused), atomic_load(&intro_open), atomic_load(&voice_mode));
        xSemaphoreGive(guard);
        return true;
    }
    if (!strncmp(line, "@lesson-demo-offline ", 21)) {
        int value;
        char tail;
        bool ok = sscanf(line + 21, "%d %c", &value, &tail) == 1 && (value == 0 || value == 1);
        if (ok) {
            atomic_store(&network_paused, value);
            if (guard) {
                xSemaphoreTake(guard, portMAX_DELAY);
                revision++;
                xSemaphoreGive(guard);
            }
        }
        printf("@mochi_lesson_offline accepted=%d simulation=%d physical_network_changed=0\n",
               ok, atomic_load(&network_paused));
        return true;
    }
    if (!strcmp(line, "@lesson-start")) {
        printf("@mochi_lesson_start accepted=%d\n", start(false));
        return true;
    }
    if (!strcmp(line, "@lesson-rest")) {
        if (guard)
            rest();
        printf("@mochi_lesson_rest accepted=%d\n", guard != NULL);
        return true;
    }
    if (!strcmp(line, "@lesson-hint")) {
        printf("@mochi_lesson_hint accepted=%d\n", hint());
        return true;
    }
    if (!strncmp(line, "@lesson-answer ", 15)) {
        int choice;
        char tail;
        bool ok = sscanf(line + 15, "%d %c", &choice, &tail) == 1 && answer(choice);
        printf("@mochi_lesson_answer accepted=%d\n", ok);
        return true;
    }
    return false;
}
