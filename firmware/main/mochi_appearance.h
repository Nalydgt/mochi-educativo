#pragma once
#include <stdbool.h>
#include <stdint.h>
typedef struct { uint8_t outfit,color,expression,motion; } mochi_appearance_t;
enum { MOCHI_LOOK_OUTFIT,MOCHI_LOOK_COLOR,MOCHI_LOOK_EXPRESSION,MOCHI_LOOK_MOTION };
void mochi_appearance_init(void);
void mochi_appearance_get(mochi_appearance_t *out);
bool mochi_appearance_set(unsigned field,unsigned value);
void mochi_appearance_cycle(unsigned field,int direction);
void mochi_appearance_poll(void);
bool mochi_appearance_flush(void);
unsigned mochi_appearance_revision(void);
const char *mochi_appearance_label(unsigned field);
const char *mochi_appearance_outfit_id(unsigned value);
bool mochi_appearance_saved(void);
