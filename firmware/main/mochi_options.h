#pragma once
#include <stdbool.h>
#include <stdint.h>
typedef enum { MOCHI_POWER_HOME, MOCHI_POWER_WALK, MOCHI_POWER_DEEP } mochi_power_mode_t;
typedef struct {
    uint32_t magic;
    char name[97], model_id[33], pending_id[33], pending_name[97];
    char public_key[160];
    float cutoff;
    uint32_t arena_bytes;
    uint8_t window, slot, power_mode;
    bool microphone, handsfree;
} mochi_options_t;
void mochi_options_init(void);
void mochi_options_get(mochi_options_t *out);
void mochi_options_poll(void);
bool mochi_options_set(const mochi_options_t *value);
void mochi_options_microphone(bool enabled);
void mochi_options_power(mochi_power_mode_t mode);
bool mochi_options_flush(void);
