#pragma once
#include "lvgl.h"
#include <stdbool.h>
#include <stddef.h>

void mochi_navigation_create(lv_obj_t *screen);
void mochi_navigation_start(void);
void mochi_navigation_session(const char *identifier);
bool mochi_navigation_visible(void);
void mochi_navigation_hide(void);
bool mochi_navigation_audio(char *route,size_t route_size,char *body,size_t body_size);
bool mochi_navigation_pointer(int x,int y,bool pressed);
void mochi_navigation_diagnose(void);
bool mochi_navigation_test(void);
bool mochi_navigation_simulation(bool enabled,double latitude,double longitude);
void mochi_navigation_simulation_lost(void);
