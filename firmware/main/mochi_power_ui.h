#pragma once
#include "lvgl.h"
#include <stdbool.h>

void mochi_power_ui_create(lv_obj_t *screen);
/* Called only from the LVGL timer. Reports a newly observed real charge. */
bool mochi_power_ui_tick(bool visible);
void mochi_power_ui_diagnose(void);
