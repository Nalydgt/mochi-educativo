#pragma once
#include "lvgl.h"
#include "mochi.h"
#include <stdbool.h>
bool mochi_animation_create(lv_obj_t *parent);
void mochi_animation_state(mochi_state_t state);
int mochi_animation_duration(mochi_state_t state);
void mochi_animation_tick(bool visible);
void mochi_animation_bind_timer(lv_timer_t *timer);
void mochi_animation_personalize(lv_obj_t *parent);
void mochi_animation_look(float x,float y);
bool mochi_animation_play(const char *id);
const char *mochi_animation_next(int direction);
unsigned mochi_animation_count(void);
const char *mochi_animation_motion_mode(void);
bool mochi_animation_motion_set(const char *mode);
bool mochi_animation_uploading(void);
bool mochi_animation_console(const char *command);
void mochi_animation_upload_poll(void);
unsigned mochi_animation_cleanup_storage(void);
