#pragma once
#include "cJSON.h"
#include <stdbool.h>
#include <stddef.h>

/* Only numeric use counters and adult settings, never a conversation, are stored. */
void mochi_education_policy_init(void);
void mochi_education_policy_apply(const cJSON *settings, double server_time);
void mochi_education_policy_tick(bool engaged);
void mochi_education_policy_flush(void);
bool mochi_education_policy_practice(void);
bool mochi_education_policy_voice(void);
bool mochi_education_policy_share(void);
bool mochi_education_policy_english(void);
bool mochi_education_policy_captions(void);
bool mochi_education_policy_text_first(void);
/* Consume a gentle display notice. Scheduling uses the same accumulated use
 * counter as the daily limit; it never changes or resets lesson progress. */
bool mochi_education_policy_next_reminder(char *text, size_t capacity);
const char *mochi_education_policy_notice(void);
void mochi_education_policy_diagnose(void);
