/*
 * Adapted from Louis-CFM/coucou windows/src/mochi/engine.ts and core/anim.ts.
 * Copyright (c) 2026 Louis Raille. MIT License, see licenses/Coucou-MIT.txt.
 * The character remains subject to licenses/Coucou-ASSETS.md.
 *
 * Original easing curves, keyframes, gaze damping, state colors, wave timings,
 * emotes, particle lifetimes and 112 BPM dance; bounded storage for ESP32.
 */
#include "coucou_motion.h"
#include <math.h>
#include <string.h>

#define PI 3.14159265358979323846f
enum { OUT, INOUT, BACK, LINEAR };
static const float colors[][3] = {
    {.902f,.914f,.933f}, {.231f,.62f,1}, {.545f,.361f,.965f},
    {.388f,.396f,.949f}, {.961f,.647f,.141f}, {.133f,.827f,.933f},
    {.957f,.314f,.369f}, {.204f,.831f,.6f}, {.984f,.573f,.235f},
    {.58f,.635f,.722f}, {.957f,.447f,.714f}
};
static const float tints[] = {0,.72f,.72f,.72f,.78f,.75f,.78f,.35f,.72f,.32f,.7f};
static const cq_eye_t eyes[] = {CQ_PILL,CQ_PILL,CQ_PILL,CQ_PILL,CQ_WIDE,CQ_PILL,CQ_FLAT,CQ_HAPPY,CQ_TIRED,CQ_CLOSED,CQ_SPIRAL};

static float random01(coucou_motion_t *m)
{
    uint32_t x = m->random;
    x ^= x << 13; x ^= x >> 17; x ^= x << 5;
    m->random = x;
    return (x & 0xffffff) / 16777216.0f;
}

static float ease(int kind, float t)
{
    if (kind == OUT) return 1 - powf(1 - t, 3);
    if (kind == INOUT) return t < .5f ? 4*t*t*t : 1 - powf(-2*t+2, 3)/2;
    if (kind == BACK) return 1 + 2.7f*powf(t-1,3) + 1.7f*powf(t-1,2);
    return t;
}

static void animate(coucou_motion_t *m, int property, const cq_key_t *keys, int count)
{
    cq_tween_t *t = &m->tween[property];
    memcpy(t->keys, keys, count * sizeof(*keys));
    t->count=count; t->index=0; t->from=m->value[property]; t->start=m->now; t->active=true;
}

#define ANIM(m,p,...) do { const cq_key_t k[] = {__VA_ARGS__}; animate(m,p,k,sizeof(k)/sizeof(k[0])); } while (0)

static void blink(coucou_motion_t *m)
{
    if (!m->tween[CQ_OPEN].active) ANIM(m,CQ_OPEN,{.06f,70,INOUT},{1,130,OUT});
}

static void emit(coucou_motion_t *m, int kind, int count)
{
    for (int n=0; n<count; n++) for (int i=0; i<24; i++) if (!m->particles[i].active) {
        cq_particle_t *p=&m->particles[i];
        *p=(cq_particle_t){.kind=kind,.x=(random01(m)-.5f)*.9f+(kind==4?.55f:0),
            .y=-.7f-random01(m)*.2f,.vx=(random01(m)-.5f)*.35f+(kind==4?.18f:0),
            .vy=-(.45f+random01(m)*.35f),.age=-n*.14f,.life=1.3f+random01(m)*.5f,
            .rotation=random01(m)*2*PI,.size=.15f+random01(m)*.08f,.active=true};
        break;
    }
}

void coucou_motion_init(coucou_motion_t *m, double now, uint32_t seed)
{
    memset(m,0,sizeof(*m));
    m->now=now; m->random=seed?seed:1; m->origin=now-random01(m)*5;
    m->value[CQ_OPEN]=m->value[CQ_SX]=m->value[CQ_SY]=m->value[CQ_ES]=1;
    m->value[CQ_OUTFIT]=1;
    m->next_blink=now+1.5+random01(m)*2;
    m->override_eye=CQ_PILL;
    memcpy(m->color,colors[CQ_IDLE],sizeof(m->color));
    memcpy(m->color_target,colors[CQ_IDLE],sizeof(m->color));
}

void coucou_motion_greet(coucou_motion_t *m)
{
    m->greeting=true; m->greet_start=m->now; m->greet_events=0;
    m->wave_start=m->now+.45; m->wave_until=m->now+1.55;
    m->override_eye=CQ_HAPPY; m->override_until=m->now+2;
    ANIM(m,CQ_OY,{-.06f,220,OUT},{0,220,BACK});
}

void coucou_motion_state(coucou_motion_t *m, cq_state_t state)
{
    m->state=state; m->eye=eyes[state]; m->value[CQ_TINT]=tints[state];
    memcpy(m->color_target,colors[state],sizeof(m->color_target));
    m->greeting=false; m->wave_until=0; m->override_until=0;
    m->gesture=0; m->gulp_start=0; m->slot_target=0; m->chewing=false; m->mini=false;
    m->value[CQ_MORPH]=0; m->tween[CQ_MORPH].active=false;
    m->value[CQ_BADGE]=0;
    ANIM(m,CQ_BADGE,{0,90,INOUT},{state==CQ_IDLE||state==CQ_SLEEPING||state==CQ_DIZZY?0:1,280,BACK});
    ANIM(m,CQ_HANDS,{0,150,INOUT});
    m->spark_at=m->yawn_at=0;
    if (state==CQ_FINISHED) { m->value[CQ_ROLL]=0; ANIM(m,CQ_ROLL,{2*PI,950,INOUT}); m->spark_at=m->now+.5; }
    else if (state==CQ_ERROR) ANIM(m,CQ_OX,{.08f,50,OUT},{-.08f,70,INOUT},{.05f,70,INOUT},{0,90,OUT});
    else if (state==CQ_APPROVAL) ANIM(m,CQ_OY,{-.2f,150,OUT},{0,300,BACK});
    else if (state==CQ_DIZZY) { m->value[CQ_ROLL]=0; ANIM(m,CQ_ROLL,{4*PI,1300,INOUT}); }
    else if(state==CQ_RATELIMIT) emit(m,3,1);
    else blink(m);
}

void coucou_motion_emote(coucou_motion_t *m, const char *name, float duration)
{
    m->override_until=m->now+duration;
    if (!strcmp(name,"love")) {
        m->override_eye=CQ_HEART;
        ANIM(m,CQ_BLUSH,{1,300,OUT},{1,(duration-.6f)*1000,LINEAR},{0,300,INOUT});
        ANIM(m,CQ_OY,{-.1f,160,OUT},{0,300,BACK}); emit(m,0,4);
    } else if (!strcmp(name,"surprised")) {
        m->override_eye=CQ_DOT;
        ANIM(m,CQ_OY,{-.3f,140,OUT},{0,380,BACK});
        ANIM(m,CQ_ES,{1.25f,120,OUT},{1,500,INOUT});
    } else if (!strcmp(name,"proud")) {
        m->override_eye=CQ_STAR; emit(m,1,5);
        ANIM(m,CQ_TILT,{-.14f,220,OUT},{-.14f,(duration-.5f)*1000,LINEAR},{0,280,INOUT});
        ANIM(m,CQ_BLUSH,{.7f,250,OUT},{.7f,(duration-.5f)*1000,LINEAR},{0,300,INOUT});
    } else if (!strcmp(name,"wink")) {
        m->override_eye=CQ_WINK;
        ANIM(m,CQ_TILT,{.12f,160,OUT},{.12f,(duration-.4f)*1000,LINEAR},{0,240,INOUT});
    } else if (!strcmp(name,"yawn")) {
        m->override_eye=CQ_TIRED;
        ANIM(m,CQ_SY,{1.12f,500,INOUT},{1,500,INOUT});
        ANIM(m,CQ_SX,{.94f,500,INOUT},{1,500,INOUT}); m->yawn_at=m->now+.7;
    } else if (!strcmp(name,"annoyed")) { m->override_eye=CQ_LINE; m->override_until=m->now+.8; }
    else { m->override_eye=CQ_HAPPY; ANIM(m,CQ_BLUSH,{.6f,200,OUT},{0,600,INOUT}); }
}

void coucou_motion_step(coucou_motion_t *m, double now)
{
    float dt=fminf(.05f,fmaxf(0,(float)(now-m->now)));
    m->now=now;
    float gesture_time=now-m->gesture_start;
    if(m->gesture==1) {
        if(gesture_time>=1 && !(m->gesture_events&1)){m->gesture_events|=1;coucou_motion_gesture(m,"gulp_inner");}
        if(gesture_time>=2.9f && !(m->gesture_events&2)){m->gesture_events|=2;ANIM(m,CQ_MORPH,{0,650,INOUT});}
    } else if(m->gesture==2) {
        m->look_x=gesture_time<.2f?0:gesture_time<1.2f?-.8f:gesture_time<2.3f?.8f:0;
        m->look_y=gesture_time<.2f?0:gesture_time<1.2f?.3f:gesture_time<2.3f?-.3f:gesture_time<3.5f?.6f:0;
    }
    if(m->gulp_start) {
        float elapsed=now-m->gulp_start;
        m->slot_target=elapsed<.46f?.42f:0;
        m->chewing=elapsed>=.46f&&elapsed<1.26f;
        if(elapsed>1.6f)m->gulp_start=0;
    }
    /* Integrate the original mouth spring in bounded substeps. */
    for(float left=dt;left>0;) {
        float step=fminf(.01f,left);left-=step;
        float omega=2*PI/.25f;
        m->slot_velocity+=(omega*omega*(m->slot_target-m->slot)-2*.6f*omega*m->slot_velocity)*step;
        m->slot=fmaxf(0,m->slot+m->slot_velocity*step);
    }
    if(m->mini && now>m->next_look) {
        m->mini_x=-.88f+random01(m)*1.76f;m->mini_y=-.55f+random01(m);
        m->next_look=now+.5+random01(m)*1.5;
    }
    if(m->mini && now>m->next_behavior) {
        if(m->permanent==6) {
            ANIM(m,CQ_OY,{-.3f,120,OUT},{.03f,200,INOUT},{0,160,BACK});
            ANIM(m,CQ_SY,{.82f,80,OUT},{1.18f,130,OUT},{.88f,160,INOUT},{1,200,BACK});
            ANIM(m,CQ_SX,{1.15f,80,OUT},{.88f,130,OUT},{1.06f,160,INOUT},{1,200,BACK});
            m->next_behavior=now+2.2+random01(m)*1.2;
        } else if(m->permanent==7) {
            ANIM(m,CQ_YAW,{-.65f,50,OUT},{.65f,90,INOUT},{-.5f,80,INOUT},{.4f,75,INOUT},{-.2f,70,INOUT},{0,140,OUT});
            m->next_behavior=now+3+random01(m)*2.5;
        } else if(m->permanent==4) {
            m->override_eye=CQ_WINK;m->override_until=now+.55;
            ANIM(m,CQ_TILT,{.13f,100,OUT},{.13f,320,LINEAR},{0,200,INOUT});
            m->next_behavior=now+2.2+random01(m)*2;
        } else if(m->permanent==1) {
            emit(m,0,2);ANIM(m,CQ_TILT,{-.1f,180,OUT},{.1f,340,INOUT},{0,220,INOUT});
            m->next_behavior=now+2.6+random01(m)*1.5;
        } else m->next_behavior=now+3+random01(m)*2;
    }
    if(m->spark_at && now>=m->spark_at) { m->spark_at=0; emit(m,2,5); }
    if(m->yawn_at && now>=m->yawn_at) { m->yawn_at=0; m->override_eye=CQ_CLOSED; emit(m,4,2); }
    if(m->extra_blink && now>=m->extra_blink) { m->extra_blink=0; blink(m); }
    if (m->greeting) {
        float elapsed=now-m->greet_start;
        if (elapsed>=.25f && !(m->greet_events&1)) {
            m->greet_events|=1;
            ANIM(m,CQ_HANDS,{1,280,OUT});
            ANIM(m,CQ_SY,{.95f,100,OUT},{1,260,BACK});
            ANIM(m,CQ_SX,{1.04f,100,OUT},{1,260,BACK});
        }
        if (elapsed>=.55f && !(m->greet_events&2)) { m->greet_events|=2; blink(m); }
        if (elapsed>=1.5f && !(m->greet_events&4)) { m->greet_events|=4; blink(m); }
        if (elapsed>=1.55f && !(m->greet_events&8)) { m->greet_events|=8; m->wave_until=0; ANIM(m,CQ_HANDS,{0,200,INOUT}); }
        if (elapsed>=1.75f && !(m->greet_events&16)) { m->greet_events|=16; m->override_eye=CQ_HAPPY; m->override_until=now+.3; }
        if (elapsed>2.1f) m->greeting=false;
    }
    for (int i=0;i<CQ_COUNT;i++) {
        cq_tween_t *tw=&m->tween[i];
        if (!tw->active) continue;
        cq_key_t *key=&tw->keys[tw->index];
        float fraction=fminf(1,fmaxf(0,(now-tw->start)*1000/fmaxf(1,key->milliseconds)));
        m->value[i]=tw->from+(key->target-tw->from)*ease(key->ease,fraction);
        if(fraction>=1) {
            tw->from=key->target; tw->start=now;
            if(++tw->index>=tw->count) { tw->active=false; if(i==CQ_ROLL) m->value[i]=0; }
        }
    }
    float t=now-m->origin, yaw=(m->mini?m->mini_x:m->look_x)*.62f, pitch=(m->mini?m->mini_y:m->look_y)*.5f;
    if (m->state==CQ_THINKING) { yaw=yaw*.35f+.55f*.55f; pitch=pitch*.3f+.55f*.5f; }
    if (m->state==CQ_SEARCHING) { yaw=sinf(t*2.6f)*.6f; pitch=-.06f; }
    if (m->state==CQ_SLEEPING) { yaw=0; pitch=-.14f; }
    if (m->state==CQ_DIZZY) yaw=sinf(t*9)*.25f;
    float tilt=m->state==CQ_QUESTION?.17f:0;
    if(now>m->wave_start && now<m->wave_until) tilt=-.06f+sinf(2*PI*1.2f*(now-m->wave_start))*.07f;
    float bounce=m->state==CQ_APPROVAL?-fabsf(sinf(t*5.2f))*.07f:0;
    float sy=m->state==CQ_SLEEPING?1+sinf(t*1.8f)*.035f:1;
    float sx=m->state==CQ_SLEEPING?1-sinf(t*1.8f)*.035f*.57f:1;
    if(m->mini && m->state!=CQ_SLEEPING){sy=1+sinf(t*2.2f)*.04f;sx=1-sinf(t*2.2f)*.02f;}
    float k=1-powf(.0008f,dt), kl=1-powf(.0025f,dt);
    const int props[]={CQ_YAW,CQ_PITCH,CQ_TILT,CQ_OY,CQ_SX,CQ_SY,CQ_ES};
    const float goals[]={yaw,pitch,tilt,bounce,sx,sy,1};
    for(int i=0;i<7;i++) if(!m->tween[props[i]].active) m->value[props[i]]+=(goals[i]-m->value[props[i]])*(i<2?kl:k);
    for(int i=0;i<3;i++) m->color[i]+=(m->color_target[i]-m->color[i])*(1-powf(.002f,dt));
    if(now>m->next_blink) {
        if(m->motion_mode!=2 && m->state!=CQ_SLEEPING && m->state!=CQ_DIZZY) {
            blink(m);
            if(random01(m)<.22f) m->extra_blink=now+.23;
        }
        m->next_blink=now+(m->motion_mode==1?6.0:2.2)+random01(m)*(m->motion_mode==1?4:3.2);
    }
    if(now-m->ambient>1.3) {
        m->ambient=now;
        if(m->state==CQ_SLEEPING) emit(m,4,1);
        if(m->state==CQ_RATELIMIT && random01(m)<.5f) emit(m,3,1);
    }
    for(int i=0;i<24;i++) if(m->particles[i].active) {
        m->particles[i].age+=dt;
        if(m->particles[i].age>=m->particles[i].life) m->particles[i].active=false;
    }
    m->dance_level=fmaxf(0,fminf(1,m->dance_level+(m->dancing?dt/.3f:-dt/.5f)));
    m->eye=now<m->override_until?m->override_eye:eyes[m->state];
    static const cq_eye_t permanent_eyes[]={CQ_PILL,CQ_HEART,CQ_DOT,CQ_STAR,CQ_WINK,CQ_TIRED,CQ_HAPPY,CQ_LINE};
    if(now>=m->override_until && m->permanent && (m->mini||m->state==CQ_IDLE))m->eye=permanent_eyes[m->permanent];
    if(m->value[CQ_MORPH]>.5f) {
        if(m->chewing)m->eye=CQ_HAPPY;
        else if(m->slot_target>.05f||m->slot>.1f)m->eye=CQ_CUP;
    }
}

void coucou_motion_permanent(coucou_motion_t *m,const char *name)
{
    static const char *const names[]={"","love","surprised","proud","wink","yawn","happy","annoyed"};
    m->permanent=0;
    for(unsigned i=1;i<8;i++)if(name&&!strcmp(name,names[i])){m->permanent=i;break;}
}
void coucou_motion_outfit(coucou_motion_t *m,bool visible)
{
    m->value[CQ_OUTFIT]=visible?0:1;
    ANIM(m,CQ_OUTFIT,{visible?1:0,visible?350:180,INOUT});
}
void coucou_motion_gesture(coucou_motion_t *m,const char *name)
{
    if(!strcmp(name,"blink")){blink(m);return;}
    if(!strcmp(name,"greet")){coucou_motion_greet(m);return;}
    if(!strcmp(name,"squash")||!strcmp(name,"slap")) {
        ANIM(m,CQ_SY,{.78f,70,OUT},{1.1f,130,OUT},{1,170,INOUT});
        ANIM(m,CQ_SX,{1.16f,70,OUT},{.95f,130,OUT},{1,170,INOUT});
        if(!strcmp(name,"slap")){m->override_eye=CQ_LINE;m->override_until=m->now+.8;}
        return;
    }
    if(!strcmp(name,"roll")){m->value[CQ_ROLL]=0;ANIM(m,CQ_ROLL,{2*PI,950,INOUT});return;}
    if(!strcmp(name,"look")){m->gesture=2;m->gesture_start=m->now;return;}
    if(!strcmp(name,"mailbox")) {
        m->gesture=1;m->gesture_start=m->now;m->gesture_events=0;
        ANIM(m,CQ_MORPH,{1,550,INOUT});return;
    }
    if(!strcmp(name,"gulp")||!strcmp(name,"gulp_inner")) {
        if(!strcmp(name,"gulp"))m->value[CQ_MORPH]=1;
        m->gulp_start=m->now;m->slot_target=.42f;
        ANIM(m,CQ_SY,{.78f,80,OUT},{1.18f,130,OUT},{1,220,BACK});
        ANIM(m,CQ_SX,{1.28f,80,OUT},{.92f,130,OUT},{1,220,BACK});blink(m);return;
    }
    if(!strcmp(name,"dance")){m->dancing=true;return;}
    if(!strcmp(name,"update_hint")){ANIM(m,CQ_BADGE,{1,280,BACK});return;}
}
