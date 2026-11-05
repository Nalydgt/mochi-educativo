/* Adult device controls. UTC comes from the authenticated educational server or
 * system time; a missing clock never becomes a fabricated school-day timestamp.
 * This does not provision flash encryption or replace the personal NVS settings. */
#include "mochi_education_policy.h"
#include "mochi_audio.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "nvs.h"
#include <math.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/time.h>
#include <time.h>

#define POLICY_MAGIC 0x45505001u
#define MIN_SAFE_TIME 1700000000LL
#define MAX_SAFE_TIME 4102444800LL
typedef struct {
    uint32_t magic, revision, used_seconds;
    int32_t day;
    uint16_t daily_minutes, start_minute, end_minute;
    int16_t utc_offset;
    bool voice, share, english, captions, text_first;
} policy_t;
/* The installed settings blob must remain readable, including used_seconds. */
_Static_assert(sizeof(policy_t) == 32 && offsetof(policy_t, used_seconds) == 8,
               "preserve the installed educational policy layout");
static policy_t policy;
static SemaphoreHandle_t mutex;
static int64_t last_tick, last_saved;
static bool dirty;
/* A separate optional NVS key extends settings without replacing the old blob. */
static uint16_t reminder_minutes = 10;
static uint32_t reminder_interval_index, warned_limit_seconds;
typedef enum { REMINDER_NONE, REMINDER_PAUSE, REMINDER_LIMIT } reminder_kind_t;
static reminder_kind_t reminder_pending;

static bool store(void) {
    nvs_handle_t handle;
    if (nvs_open("mochi_policy", NVS_READWRITE, &handle) != ESP_OK)
        return false;
    esp_err_t result = nvs_set_blob(handle, "settings", &policy, sizeof(policy));
    if (result == ESP_OK)
        result = nvs_set_u16(handle, "reminder_min", reminder_minutes);
    if (result == ESP_OK)
        result = nvs_commit(handle);
    nvs_close(handle);
    if (result == ESP_OK) {
        dirty = false;
        last_saved = esp_timer_get_time();
    }
    return result == ESP_OK;
}
static bool clock_now(int64_t *value) {
    int64_t instant = (int64_t)time(NULL);
    if (instant < MIN_SAFE_TIME || instant > MAX_SAFE_TIME)
        return false;
    *value = instant + (int64_t)policy.utc_offset * 60;
    return true;
}
static bool inside_hours(bool *clock_known) {
    int64_t now;
    *clock_known = clock_now(&now);
    if (policy.start_minute == policy.end_minute)
        return true;
    if (!*clock_known)
        return false;
    unsigned minute = (unsigned)((now % 86400) / 60);
    return policy.start_minute < policy.end_minute
        ? minute >= policy.start_minute && minute < policy.end_minute
        : minute >= policy.start_minute || minute < policy.end_minute;
}
static bool allowed(void) {
    bool known;
    return policy.used_seconds < (uint32_t)policy.daily_minutes * 60 && inside_hours(&known);
}
static void rebase_reminder(void) {
    reminder_interval_index = reminder_minutes
        ? policy.used_seconds / ((uint32_t)reminder_minutes * 60) : 0;
}
static void schedule_reminder(bool engaged) {
    uint32_t limit = (uint32_t)policy.daily_minutes * 60;
    if (!engaged || !allowed()) {
        if (policy.used_seconds >= limit)
            reminder_pending = REMINDER_NONE;
        return;
    }
    uint32_t remaining = limit - policy.used_seconds;
    /* The closing warning belongs to the daily limit, even when the family
     * disables periodic reminders. A shorter daily allowance gets one warning. */
    if (remaining <= 300 && warned_limit_seconds != limit) {
        warned_limit_seconds = limit;
        reminder_pending = REMINDER_LIMIT;
    }
    if (reminder_minutes) {
        uint32_t index = policy.used_seconds / ((uint32_t)reminder_minutes * 60);
        if (index > reminder_interval_index) {
            reminder_interval_index = index;
            if (reminder_pending != REMINDER_LIMIT)
                reminder_pending = REMINDER_PAUSE;
        }
    }
}
static bool number(const cJSON *object, const char *name, int low, int high, int *value) {
    const cJSON *item = cJSON_GetObjectItemCaseSensitive(object, name);
    if (!cJSON_IsNumber(item) || item->valuedouble != item->valueint || item->valueint < low || item->valueint > high)
        return false;
    *value = item->valueint;
    return true;
}
static bool minute(const cJSON *object, const char *name, uint16_t *value) {
    const cJSON *item = cJSON_GetObjectItemCaseSensitive(object, name);
    if (!cJSON_IsString(item) || strlen(item->valuestring) != 5 || item->valuestring[2] != ':')
        return false;
    const char *s = item->valuestring;
    if (s[0] < '0' || s[0] > '2' || s[1] < '0' || s[1] > '9' ||
        s[3] < '0' || s[3] > '5' || s[4] < '0' || s[4] > '9')
        return false;
    int hours = (s[0] - '0') * 10 + s[1] - '0';
    if (hours > 23)
        return false;
    *value = hours * 60 + (s[3] - '0') * 10 + s[4] - '0';
    return true;
}
void mochi_education_policy_init(void) {
    mutex = xSemaphoreCreateMutex();
    policy = (policy_t){.magic = POLICY_MAGIC, .daily_minutes = 60, .voice = true, .share = true, .captions = true};
    reminder_minutes = 10;
    reminder_pending = REMINDER_NONE;
    warned_limit_seconds = 0;
    dirty = false;
    nvs_handle_t handle;
    if (nvs_open("mochi_policy", NVS_READONLY, &handle) == ESP_OK) {
        policy_t stored;
        size_t bytes = sizeof(stored);
        if (nvs_get_blob(handle, "settings", &stored, &bytes) == ESP_OK && bytes == sizeof(stored) &&
            stored.magic == POLICY_MAGIC && stored.daily_minutes >= 1 && stored.daily_minutes <= 240 &&
            stored.start_minute < 1440 && stored.end_minute < 1440 && stored.utc_offset >= -840 &&
            stored.utc_offset <= 840 && stored.used_seconds <= 86400 && stored.day >= 0)
            policy = stored;
        uint16_t stored_reminder;
        if (nvs_get_u16(handle, "reminder_min", &stored_reminder) == ESP_OK &&
            (stored_reminder == 0 || (stored_reminder >= 5 && stored_reminder <= 60)))
            reminder_minutes = stored_reminder;
        nvs_close(handle);
    }
    rebase_reminder();
    last_tick = last_saved = esp_timer_get_time();
}
void mochi_education_policy_apply(const cJSON *settings, double server_time) {
    if (!mutex)
        return;
    /* Server time is trusted only after the authenticated event fetch succeeds. */
    if (isfinite(server_time) && server_time >= MIN_SAFE_TIME && server_time <= MAX_SAFE_TIME) {
        struct timeval value = {.tv_sec = (time_t)server_time};
        settimeofday(&value, NULL);
    }
    if (!cJSON_IsObject(settings))
        return;
    xSemaphoreTake(mutex, portMAX_DELAY);
    policy_t next = policy;
    int daily, revision, offset, next_reminder = reminder_minutes;
    const cJSON *voice = cJSON_GetObjectItemCaseSensitive(settings, "voiceEnabled");
    const cJSON *share = cJSON_GetObjectItemCaseSensitive(settings, "sharePractice");
    const cJSON *language = cJSON_GetObjectItemCaseSensitive(settings, "language");
    const cJSON *captions = cJSON_GetObjectItemCaseSensitive(settings, "captionsEnabled");
    if (!captions)
        captions = cJSON_GetObjectItemCaseSensitive(settings, "captionMode");
    const cJSON *text_first = cJSON_GetObjectItemCaseSensitive(settings, "textFirst");
    const cJSON *reminder = cJSON_GetObjectItemCaseSensitive(settings, "reminderMinutes");
    bool reminder_valid = !reminder || cJSON_IsNull(reminder) ||
        number(settings, "reminderMinutes", 5, 60, &next_reminder);
    if (cJSON_IsNull(reminder))
        next_reminder = 0;
    bool valid = number(settings, "dailyMinutes", 1, 240, &daily) &&
        number(settings, "revision", 0, 2147483647, &revision) &&
        number(settings, "utcOffsetMinutes", -840, 840, &offset) &&
        minute(settings, "startTime", &next.start_minute) && minute(settings, "endTime", &next.end_minute) &&
        cJSON_IsBool(voice) && cJSON_IsBool(share) && cJSON_IsString(language) &&
        (!strcmp(language->valuestring, "es") || !strcmp(language->valuestring, "en") ||
         !strcmp(language->valuestring, "pt")) && reminder_valid;
    if (valid && (uint32_t)revision >= policy.revision) {
        next.daily_minutes = daily;
        next.revision = revision;
        next.utc_offset = offset;
        next.voice = cJSON_IsTrue(voice);
        next.share = cJSON_IsTrue(share);
        next.english = !strcmp(language->valuestring, "en");
        if (cJSON_IsBool(captions))
            next.captions = cJSON_IsTrue(captions);
        if (cJSON_IsBool(text_first))
            next.text_first = cJSON_IsTrue(text_first);
        if (memcmp(&next, &policy, sizeof(policy)) || next_reminder != reminder_minutes) {
            bool interval_changed = next_reminder != reminder_minutes;
            bool limit_changed = next.daily_minutes != policy.daily_minutes;
            policy = next;
            reminder_minutes = next_reminder;
            if (interval_changed) {
                rebase_reminder();
                if (reminder_pending == REMINDER_PAUSE)
                    reminder_pending = REMINDER_NONE;
            }
            if (limit_changed) {
                warned_limit_seconds = 0;
                reminder_pending = REMINDER_NONE;
            }
            dirty = true;
            store();
        }
    }
    xSemaphoreGive(mutex);
}
void mochi_education_policy_tick(bool engaged) {
    if (!mutex)
        return;
    int64_t now = esp_timer_get_time();
    xSemaphoreTake(mutex, portMAX_DELAY);
    int64_t trusted;
    if (clock_now(&trusted)) {
        int32_t day = trusted / 86400;
        if (!policy.day) {
            /* Retain any un-dated use instead of granting a second allowance. */
            policy.day = day;
            dirty = true;
        } else if (day > policy.day) {
            policy.day = day;
            policy.used_seconds = 0;
            reminder_interval_index = 0;
            warned_limit_seconds = 0;
            reminder_pending = REMINDER_NONE;
            dirty = true;
        }
    }
    int64_t delta = now - last_tick;
    if (delta >= 1000000) {
        unsigned seconds = delta / 1000000;
        last_tick += (int64_t)seconds * 1000000;
        if (engaged && allowed()) {
            uint32_t used = policy.used_seconds + seconds;
            policy.used_seconds = used > 86400 ? 86400 : used;
            dirty = true;
        }
    }
    schedule_reminder(engaged);
    if (dirty && now - last_saved >= 60000000)
        store();
    xSemaphoreGive(mutex);
}
void mochi_education_policy_flush(void) {
    if (!mutex)
        return;
    xSemaphoreTake(mutex, portMAX_DELAY);
    if (dirty)
        store();
    xSemaphoreGive(mutex);
}
bool mochi_education_policy_practice(void) {
    if (!mutex)
        return false;
    xSemaphoreTake(mutex, portMAX_DELAY);
    bool result = allowed();
    xSemaphoreGive(mutex);
    return result;
}
bool mochi_education_policy_voice(void) {
    if (!mutex)
        return false;
    xSemaphoreTake(mutex, portMAX_DELAY);
    bool result = policy.voice && allowed();
    xSemaphoreGive(mutex);
    return result;
}
bool mochi_education_policy_share(void) {
    if (!mutex)
        return false;
    xSemaphoreTake(mutex, portMAX_DELAY);
    bool value = policy.share;
    xSemaphoreGive(mutex);
    return value;
}
bool mochi_education_policy_english(void) {
    if (!mutex)
        return false;
    xSemaphoreTake(mutex, portMAX_DELAY);
    bool value = policy.english;
    xSemaphoreGive(mutex);
    return value;
}
bool mochi_education_policy_captions(void) {
    if (!mutex)
        return true;
    xSemaphoreTake(mutex, portMAX_DELAY);
    /* Muting output never removes the visible response. This is an effective
     * accessibility fallback, not a change to the adult's saved preference. */
    bool value = policy.captions || policy.text_first || mochi_audio_get_volume() == 0;
    xSemaphoreGive(mutex);
    return value;
}
bool mochi_education_policy_text_first(void) {
    if (!mutex)
        return false;
    xSemaphoreTake(mutex, portMAX_DELAY);
    bool value = policy.text_first;
    xSemaphoreGive(mutex);
    return value;
}
bool mochi_education_policy_next_reminder(char *text, size_t capacity) {
    if (!mutex || !text || !capacity)
        return false;
    xSemaphoreTake(mutex, portMAX_DELAY);
    bool ready = reminder_pending != REMINDER_NONE && allowed();
    if (ready) {
        if (reminder_pending == REMINDER_LIMIT) {
            unsigned left = ((uint32_t)policy.daily_minutes * 60 - policy.used_seconds + 59) / 60;
            snprintf(text, capacity, policy.english
                ? "About %u min left today.\nYour progress is safe."
                : "Quedan %u min por hoy.\nTu progreso está guardado.", left);
        } else {
            snprintf(text, capacity, policy.english
                ? "We have spent %u min together.\nA little break?"
                : "Llevamos %u min juntos.\n¿Hacemos una pausa?", (unsigned)(policy.used_seconds / 60));
        }
        reminder_pending = REMINDER_NONE;
    } else if (!allowed()) {
        reminder_pending = REMINDER_NONE;
    }
    xSemaphoreGive(mutex);
    return ready;
}
const char *mochi_education_policy_notice(void) {
    if (!mutex)
        return "No pude preparar los límites. Pide ayuda a un adulto.";
    xSemaphoreTake(mutex, portMAX_DELAY);
    bool known;
    bool hours = inside_hours(&known);
    const char *notice = policy.used_seconds >= (uint32_t)policy.daily_minutes * 60
        ? (policy.english ? "Time to rest. Your progress is safe for another day." : "Es hora de descansar. Tu progreso queda guardado para otro día.")
        : !hours && !known
            ? (policy.english ? "I need a reliable clock. Connect or ask an adult for help." : "Necesito una hora segura. Conecta o pide ayuda a un adulto.")
            : !hours
                ? (policy.english ? "We are outside your learning hours. Your progress is safe." : "Estamos fuera de tu horario. Tu progreso sigue guardado.")
                : !policy.voice
                    ? (policy.english ? "Voice is turned off by your adult. You can keep learning here." : "Tu adulto ha desactivado la voz. Podemos seguir aprendiendo aquí.") : "";
    xSemaphoreGive(mutex);
    return notice;
}
void mochi_education_policy_diagnose(void) {
    if (!mutex) {
        printf("@mochi_education_policy ready=0\n");
        return;
    }
    xSemaphoreTake(mutex, portMAX_DELAY);
    int64_t ignored;
    printf("@mochi_education_policy ready=1 revision=%lu daily_minutes=%u used_seconds=%lu clock=%d allowed=%d voice=%d share=%d captions=%d text_first=%d reminder_minutes=%u reminder_pending=%d\n",
        (unsigned long)policy.revision, policy.daily_minutes, (unsigned long)policy.used_seconds,
        clock_now(&ignored), allowed(), policy.voice, policy.share,
        policy.captions || policy.text_first || mochi_audio_get_volume() == 0, policy.text_first,
        reminder_minutes, reminder_pending);
    xSemaphoreGive(mutex);
}
