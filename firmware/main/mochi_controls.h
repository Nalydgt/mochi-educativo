#pragma once
#include <stdbool.h>

void mochi_controls_init(void);
void mochi_controls_poll(void);
bool mochi_controls_request_off(void);
bool mochi_controls_power_pending(void);
void mochi_controls_diagnose(void);
typedef struct { bool valid,usb,charging; int percent,millivolts; } mochi_power_status_t;
void mochi_controls_power_status(mochi_power_status_t *out);
void mochi_controls_request_deep(void);
