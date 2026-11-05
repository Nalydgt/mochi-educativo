#pragma once

#include "cJSON.h"
#include "lvgl.h"
#include <stdbool.h>

/* Guided, deterministic exercises. No language model runs on the ESP32. */
void mochi_lessons_create(lv_obj_t *parent);
void mochi_lessons_tick(bool visible);
bool mochi_lessons_interacting(void);
bool mochi_lessons_voice_passthrough(void);
/* Deliberate hold begins capture intent; these never open the microphone. */
bool mochi_lessons_voice_begin(void);
void mochi_lessons_voice_end(void);
void mochi_lessons_voice_state(int state);
void mochi_lessons_voice_caption(const char *text);
/* Zero-based step, bound to the exact downloaded lesson. */
bool mochi_lessons_voice_context(char lesson_id[37], int *step, int *a, int *b);
bool mochi_lessons_spoken_answer(const char *lesson_id, int step, int choice);
bool mochi_lessons_pending_question(char lesson_id[37], int *step);
void mochi_lessons_question_announced(const char *lesson_id, int step);
bool mochi_lessons_network_paused(void);
void mochi_lessons_connection(bool available);
bool mochi_lessons_offer(const cJSON *package);
cJSON *mochi_lessons_pending_result(void);
bool mochi_lessons_acknowledge(const char *result_id);
bool mochi_lessons_forget(void);
bool mochi_lessons_console(const char *line);
