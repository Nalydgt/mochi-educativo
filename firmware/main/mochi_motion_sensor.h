#pragma once
#include <stdbool.h>
void mochi_motion_sensor_init(void);
void mochi_motion_sensor_poll(void);
bool mochi_motion_sensor_get(float *x,float *y,float *z);
bool mochi_motion_sensor_lifted(void);
