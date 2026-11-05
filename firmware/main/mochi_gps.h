#pragma once
#include <stdbool.h>
#include <stdint.h>

typedef struct {
    double latitude, longitude;
    bool detected, fix, available;
    int satellites, age_seconds;
    uint32_t sentences, errors;
} mochi_gps_status_t;

void mochi_gps_start(void);
void mochi_gps_request(void);
void mochi_gps_tracking(bool enabled);
void mochi_gps_status(mochi_gps_status_t *out);
void mochi_gps_diagnose(void);
bool mochi_gps_self_test(void);
