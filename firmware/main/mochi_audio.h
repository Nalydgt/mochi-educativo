#pragma once
#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"

#define MOCHI_SAMPLE_RATE 16000
#define MOCHI_AUDIO_FRAMES 256
esp_err_t mochi_audio_init(void);
void mochi_audio_idle(void);
void mochi_audio_diagnose(void);
bool mochi_audio_self_test(void);
esp_err_t mochi_audio_read(int16_t *mono, size_t frames);
esp_err_t mochi_audio_write(const int16_t *mono, size_t frames);
int mochi_audio_get_volume(void);
void mochi_audio_set_volume(int percent);

typedef struct {
    unsigned level_q10,mean_abs,age_ms,sequence;
    unsigned first_nonzero_tick;
    bool first_nonzero_seen;
    bool active,tap_ready;
} mochi_output_status_t;
/* Actual completed I2S DMA output, never the queued network input. */
void mochi_audio_output_status(mochi_output_status_t *out);
unsigned mochi_audio_output_level(void);
