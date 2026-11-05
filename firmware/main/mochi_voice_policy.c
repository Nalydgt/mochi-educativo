#include "mochi_voice_policy.h"
#include <math.h>
#include <string.h>

void mochi_vad_init(mochi_vad_t *vad,float noise)
{
    memset(vad,0,sizeof(*vad)); vad->noise=fmaxf(40,noise);
}
bool mochi_vad_voiced(const int16_t *pcm,size_t frames,float noise)
{
    if (!frames) return false;
    double energy=0; for (size_t i=0;i<frames;i++) energy+=(double)pcm[i]*pcm[i];
    return sqrt(energy/frames)>fmaxf(180,noise*3);
}
mochi_vad_result_t mochi_vad_step(mochi_vad_t *vad,const int16_t *pcm,size_t frames,uint32_t waiting_ms)
{
    bool voiced=mochi_vad_voiced(pcm,frames,vad->noise);
    vad->elapsed+=frames;
    if (voiced) {
        vad->speech+=frames; vad->silence=0;
        if (vad->speech>=1600) vad->heard=true;
    } else {
        vad->silence+=frames;
        /* Isolated clicks must not accumulate into a speech onset. */
        if (!vad->heard && vad->silence>=1024) vad->speech=0;
    }
    if (!vad->heard && vad->elapsed>=waiting_ms*16) return MOCHI_VAD_EMPTY;
    if (vad->heard && vad->silence>=11200) return MOCHI_VAD_COMPLETE;
    return vad->elapsed>=128000 ? (vad->heard?MOCHI_VAD_LIMIT:MOCHI_VAD_EMPTY) : MOCHI_VAD_MORE;
}
bool mochi_voice_policy_self_test(void)
{
    mochi_vad_t v; int16_t pcm[160];
    mochi_vad_init(&v,40); memset(pcm,0,sizeof(pcm));
    for (int i=0;i<399;i++) if (mochi_vad_step(&v,pcm,160,4000)!=MOCHI_VAD_MORE) return false;
    if (mochi_vad_step(&v,pcm,160,4000)!=MOCHI_VAD_EMPTY) return false;
    mochi_vad_init(&v,40);
    for (int i=0;i<160;i++) pcm[i]=i%2?1000:-1000;
    for (int i=0;i<30;i++) if (mochi_vad_step(&v,pcm,160,8000)!=MOCHI_VAD_MORE) return false;
    memset(pcm,0,sizeof(pcm));
    for (int i=0;i<69;i++) if (mochi_vad_step(&v,pcm,160,8000)!=MOCHI_VAD_MORE) return false;
    if (mochi_vad_step(&v,pcm,160,8000)!=MOCHI_VAD_COMPLETE) return false;
    /* Follow-up stays open for eight seconds despite isolated noise clicks. */
    mochi_vad_init(&v,40);
    for (int i=0;i<800;i++) {
        for (int j=0;j<160;j++) pcm[j]=(i%100==20)?(j%2?1000:-1000):0;
        mochi_vad_result_t result=mochi_vad_step(&v,pcm,160,8000);
        if (v.heard || result!=(i==799?MOCHI_VAD_EMPTY:MOCHI_VAD_MORE)) return false;
    }
    /* Speech starting near the end of the window is still accepted. */
    mochi_vad_init(&v,40); memset(pcm,0,sizeof(pcm));
    for (int i=0;i<770;i++) if (mochi_vad_step(&v,pcm,160,8000)!=MOCHI_VAD_MORE) return false;
    for (int j=0;j<160;j++) pcm[j]=j%2?1000:-1000;
    for (int i=0;i<10;i++) if (mochi_vad_step(&v,pcm,160,8000)!=MOCHI_VAD_MORE) return false;
    if (!v.heard) return false;
    v.elapsed=16000; /* runtime keeps only the one-second pre-roll */
    for (int i=0;i<30;i++) if (mochi_vad_step(&v,pcm,160,8000)!=MOCHI_VAD_MORE) return false;
    memset(pcm,0,sizeof(pcm));
    for (int i=0;i<69;i++) if (mochi_vad_step(&v,pcm,160,8000)!=MOCHI_VAD_MORE) return false;
    return mochi_vad_step(&v,pcm,160,8000)==MOCHI_VAD_COMPLETE;
}
