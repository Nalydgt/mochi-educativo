#pragma once
#include "lvgl.h"
#include <stdbool.h>
#include <stdint.h>

typedef enum { MOCHI_SCENE_GROUPS, MOCHI_SCENE_COMPLETE, MOCHI_SCENE_VOICE, MOCHI_SCENE_HUB } mochi_lesson_scene_mode_t;
/* One native surface, no bitmap frames or per-item LVGL allocation.
 * zero-based progress % 3: apples, fish, toy cars. */
lv_obj_t *mochi_lesson_scene_create(lv_obj_t *parent, int y);
void mochi_lesson_scene_decorate_launcher(lv_obj_t *button);
void mochi_lesson_scene_set(mochi_lesson_scene_mode_t mode, unsigned groups, unsigned quantity,
                            unsigned hint, unsigned progress, unsigned total, bool active);
void mochi_lesson_scene_tick(int64_t now, unsigned motion, bool visible);
void mochi_lesson_scene_diagnose(void);
