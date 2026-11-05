#pragma once
#include "lvgl.h"
#include <stdbool.h>
void mochi_education_text_create(lv_obj_t *parent);
void mochi_education_text_show(void);
void mochi_education_text_tick(bool enabled);
bool mochi_education_text_active(void);
bool mochi_education_text_busy(void);
