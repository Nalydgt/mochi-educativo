#pragma once
#include "lvgl.h"

typedef enum {
    MOCHI_IDLE, MOCHI_HAPPY, MOCHI_LOVE, MOCHI_SURPRISED, MOCHI_SAD,
    MOCHI_SLEEPING, MOCHI_THINKING, MOCHI_CURIOUS, MOCHI_PROUD,
    MOCHI_WINK, MOCHI_DIZZY, MOCHI_LISTENING, MOCHI_SPEAKING, MOCHI_OFFLINE,
    MOCHI_WORKING, MOCHI_SEARCHING, MOCHI_APPROVAL, MOCHI_FINISHED,
    MOCHI_RATELIMIT, MOCHI_YAWN, MOCHI_ANNOYED, MOCHI_DANCING, MOCHI_STATE_COUNT
} mochi_state_t;

void mochi_create(lv_obj_t *screen);
void mochi_greet(void);
void mochi_toggle_sleep(void);
void mochi_set_state(mochi_state_t state, int duration_ms);
mochi_state_t mochi_state_from_name(const char *name);
/* Thread-safe envelope mailbox. Never waits for LVGL or draws from audio. */
void mochi_set_audio_level(float level);
void mochi_show_notice(const char *text, int duration_ms);
void mochi_set_voice_handlers(void (*start)(void), void (*stop)(void), bool (*busy)(void));
void mochi_settings_set_open(bool open);
/* Use the exact original Mochi gestures on additional transparent surfaces. */
bool mochi_interaction_blocked(void);
