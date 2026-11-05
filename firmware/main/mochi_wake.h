#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"
#ifdef __cplusplus
extern "C" {
#endif
/* Only the audio owner calls load/reset/feed. No background task reads I2S. */
esp_err_t mochi_wake_load(const char *path, float cutoff, unsigned window, size_t arena_bytes);
void mochi_wake_unload(void);
void mochi_wake_reset(void);
bool mochi_wake_feed(const int16_t *pcm, size_t frames);
bool mochi_wake_ready(void);
void mochi_wake_diagnose(void);
#ifdef __cplusplus
}
#endif
