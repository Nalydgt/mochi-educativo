#pragma once

#include <stdbool.h>
#include "lvgl.h"

/* Mutating functions run on the LVGL task, or with the display lock held. */
void mochi_wifi_ui_create(lv_obj_t *screen);
void mochi_wifi_ui_open(void);
void mochi_wifi_ui_close(void);
bool mochi_wifi_ui_is_open(void); /* Atomic read; safe from voice/control tasks. */
/* Diagnostic previews contain no saved credentials and do not start Wi-Fi work. */
void mochi_wifi_ui_preview(const char *page);
