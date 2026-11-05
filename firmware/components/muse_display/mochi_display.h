#pragma once
#include "lvgl.h"

lv_display_t *mochi_display_start(void);
void mochi_display_activity(void);
void mochi_display_poll(bool portable,bool force_awake);
void mochi_display_diagnose(void);
bool mochi_display_test(void);
bool mochi_display_awake(void);
