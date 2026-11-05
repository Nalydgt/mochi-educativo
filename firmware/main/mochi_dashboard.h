#pragma once
#include "lvgl.h"
#include <stdbool.h>
void mochi_dashboard_create(lv_obj_t *screen);
void mochi_dashboard_open(void);
void mochi_dashboard_close(void);
bool mochi_dashboard_is_open(void);
bool mochi_dashboard_preview_active(void);
void mochi_dashboard_show(unsigned page);
bool mochi_dashboard_pointer(int x,int y,bool pressed);
void mochi_dashboard_diagnose(void);
