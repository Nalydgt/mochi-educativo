#pragma once
#include <stdbool.h>
#include <stdint.h>

/* Port of Coucou BotEngine's non-mini motion state. Times are in seconds. */
enum { CQ_YAW, CQ_PITCH, CQ_ROLL, CQ_TILT, CQ_OPEN, CQ_SX, CQ_SY,
       CQ_OY, CQ_OX, CQ_TINT, CQ_HANDS, CQ_BLUSH, CQ_ES, CQ_MORPH, CQ_OUTFIT, CQ_BADGE, CQ_COUNT };
typedef enum { CQ_PILL, CQ_WIDE, CQ_DOT, CQ_LINE, CQ_FLAT, CQ_HAPPY,
    CQ_CLOSED, CQ_SPIRAL, CQ_HEART, CQ_STAR, CQ_TIRED, CQ_WINK, CQ_CUP } cq_eye_t;
typedef enum { CQ_IDLE, CQ_WORKING, CQ_THINKING, CQ_SEARCHING, CQ_APPROVAL,
    CQ_QUESTION, CQ_ERROR, CQ_FINISHED, CQ_RATELIMIT, CQ_SLEEPING, CQ_DIZZY } cq_state_t;
typedef struct { float target, milliseconds; uint8_t ease; } cq_key_t;
typedef struct { cq_key_t keys[8]; int count, index; float from; double start; bool active; } cq_tween_t;
typedef struct { int kind; float x,y,vx,vy,age,life,rotation,size; bool active; } cq_particle_t;
typedef struct {
    float value[CQ_COUNT], look_x, look_y, color[3], color_target[3];
    cq_tween_t tween[CQ_COUNT];
    cq_particle_t particles[24];
    cq_state_t state;
    cq_eye_t eye, override_eye;
    double now, origin, next_blink, override_until, wave_start, wave_until, greet_start, ambient;
    double extra_blink, spark_at, yawn_at;
    uint32_t random;
    unsigned greet_events;
    bool greeting, dancing;
    float dance_level;
    double gesture_start,gulp_start,next_behavior,next_look;
    unsigned gesture,gesture_events,permanent,motion_mode;
    float slot,slot_target,slot_velocity,mini_x,mini_y;
    bool mini,chewing;
} coucou_motion_t;

void coucou_motion_init(coucou_motion_t *motion, double now, uint32_t seed);
void coucou_motion_state(coucou_motion_t *motion, cq_state_t state);
void coucou_motion_emote(coucou_motion_t *motion, const char *name, float duration);
void coucou_motion_greet(coucou_motion_t *motion);
void coucou_motion_step(coucou_motion_t *motion, double now);
void coucou_motion_gesture(coucou_motion_t *motion,const char *name);
void coucou_motion_permanent(coucou_motion_t *motion,const char *name);
void coucou_motion_outfit(coucou_motion_t *motion,bool visible);
