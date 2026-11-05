#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef struct {
    uint32_t elapsed, silence, speech;
    float noise;
    bool heard;
} mochi_vad_t;
typedef enum { MOCHI_VAD_MORE, MOCHI_VAD_COMPLETE, MOCHI_VAD_EMPTY, MOCHI_VAD_LIMIT } mochi_vad_result_t;
void mochi_vad_init(mochi_vad_t *vad, float noise);
bool mochi_vad_voiced(const int16_t *pcm,size_t frames,float noise);
mochi_vad_result_t mochi_vad_step(mochi_vad_t *vad,const int16_t *pcm,size_t frames,uint32_t waiting_ms);
bool mochi_voice_policy_self_test(void);
