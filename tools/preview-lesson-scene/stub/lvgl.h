#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#define LV_RADIUS_CIRCLE 0x7FFF
typedef uint32_t lv_color_t;
typedef uint8_t lv_opa_t;
typedef struct {int x,y,w,h;} lv_obj_t;
typedef struct {int unused;} lv_layer_t;
typedef struct {int size;} lv_font_t;
typedef struct {int x,y;} lv_point_precise_t;
typedef struct {int x1,y1,x2,y2;} lv_area_t;
#define LV_RADIUS_CIRCLE 0x7fff
typedef struct {lv_obj_t *target;} lv_event_t;
typedef struct {lv_color_t bg_color,border_color;lv_opa_t bg_opa,border_opa;int radius,border_width;} lv_draw_rect_dsc_t;
typedef struct {const char *text;bool text_local;const lv_font_t *font;int align;lv_color_t color;lv_opa_t opa;} lv_draw_label_dsc_t;
typedef struct {lv_point_precise_t p1,p2;int width;lv_color_t color;lv_opa_t opa;bool round_start,round_end;} lv_draw_line_dsc_t;
typedef struct {lv_point_precise_t p[3];lv_color_t color;lv_opa_t opa;} lv_draw_triangle_dsc_t;
enum {LV_TEXT_ALIGN_CENTER,LV_ALIGN_TOP_MID,LV_OBJ_FLAG_CLICKABLE=1,LV_OBJ_FLAG_SCROLLABLE=2,LV_EVENT_DRAW_MAIN=9};
static inline lv_color_t lv_color_hex(uint32_t value){return value;}
void lv_draw_rect(lv_layer_t*,const lv_draw_rect_dsc_t*,const lv_area_t*);
void lv_draw_label(lv_layer_t*,const lv_draw_label_dsc_t*,const lv_area_t*);
void lv_draw_line(lv_layer_t*,const lv_draw_line_dsc_t*);
void lv_draw_triangle(lv_layer_t*,const lv_draw_triangle_dsc_t*);
#define lv_draw_rect_dsc_init(d) memset((d),0,sizeof(*(d)))
#define lv_draw_label_dsc_init(d) memset((d),0,sizeof(*(d)))
#define lv_draw_line_dsc_init(d) memset((d),0,sizeof(*(d)))
#define lv_draw_triangle_dsc_init(d) memset((d),0,sizeof(*(d)))
lv_obj_t *lv_obj_create(lv_obj_t*);
static inline void lv_obj_remove_style_all(lv_obj_t *o){(void)o;}
static inline void lv_obj_set_size(lv_obj_t *o,int w,int h){o->w=w;o->h=h;}
static inline void lv_obj_align(lv_obj_t *o,int align,int x,int y){(void)align;o->x=233-o->w/2+x;o->y=y;}
static inline void lv_obj_remove_flag(lv_obj_t *o,int flag){(void)o;(void)flag;}
static inline void lv_obj_add_event_cb(lv_obj_t *o,void(*cb)(lv_event_t*),int code,void *data){(void)o;(void)cb;(void)code;(void)data;}
static inline void lv_obj_invalidate(lv_obj_t *o){(void)o;}
static inline void lv_obj_get_coords(lv_obj_t *o,lv_area_t *a){*a=(lv_area_t){o->x,o->y,o->x+o->w-1,o->y+o->h-1};}
static inline int lv_obj_get_height(lv_obj_t *o){return o->h;}
static inline lv_layer_t *lv_event_get_layer(lv_event_t *e){(void)e;return 0;}
static inline lv_obj_t *lv_event_get_target(lv_event_t *e){return e->target;}
