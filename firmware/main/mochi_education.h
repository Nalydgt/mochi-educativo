#pragma once
#include "lvgl.h"
#include "mochi.h"
#include "cJSON.h"
#include <stdbool.h>
#include <stddef.h>
void mochi_education_create(lv_obj_t *parent);
bool mochi_education_active(void);
bool mochi_education_blocked(void);
bool mochi_education_pointer(int x, int y, bool pressed);
void mochi_education_notice(const char *text, int duration_ms);
bool mochi_education_enter(void);
/* Opens sound controls without a PIN; protected adult actions keep their PIN. */
void mochi_education_options(void);
void mochi_education_state(mochi_state_t state);
bool mochi_education_console(const char *line);
bool mochi_education_credentials(char *url, size_t url_size, char *token, size_t token_size);
bool mochi_education_voice_allowed(void);
bool mochi_education_practice_allowed(void);
bool mochi_education_share_practice(void);
const char *mochi_education_policy_notice(void);
void mochi_education_apply_settings(const cJSON *settings, double server_time);
/* Transient full captions, never written to NVS or shared as conversation logs. */
void mochi_education_caption(const char *text);
