/* Keep the GUI heap in PSRAM so its small objects cannot fragment the
 * internal RAM required by Wi-Fi, I2S DMA and the VPN task stacks. */
#include "lvgl.h"
#include "mochi_lv_memory.h"
#include "esp_heap_caps.h"
#include <stdlib.h>
#include <string.h>

bool mochi_lv_memory_ready(void)
{
    /* Called before lv_init; it also anchors this custom backend in the
     * display archive before LVGL's allocator references are linked. */
    return heap_caps_get_total_size(MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT)>0;
}

#if LV_USE_STDLIB_MALLOC == LV_STDLIB_CUSTOM
#define GUI_CAPS (MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT)
void lv_mem_init(void){}
void lv_mem_deinit(void){}
lv_mem_pool_t lv_mem_add_pool(void *memory,size_t bytes){(void)memory;(void)bytes;return NULL;}
void lv_mem_remove_pool(lv_mem_pool_t pool){(void)pool;}
void *lv_malloc_core(size_t size){return heap_caps_malloc(size,GUI_CAPS);}
void *lv_realloc_core(void *memory,size_t size){return heap_caps_realloc(memory,size,GUI_CAPS);}
void lv_free_core(void *memory){heap_caps_free(memory);}
void lv_mem_monitor_core(lv_mem_monitor_t *monitor)
{
    /* This is the shared external heap, including non-GUI PSRAM buffers. */
    multi_heap_info_t heap;heap_caps_get_info(&heap,GUI_CAPS);
    memset(monitor,0,sizeof(*monitor));
    monitor->total_size=heap_caps_get_total_size(GUI_CAPS);
    monitor->free_size=heap.total_free_bytes;monitor->free_cnt=heap.free_blocks;
    monitor->free_biggest_size=heap.largest_free_block;monitor->used_cnt=heap.allocated_blocks;
    monitor->max_used=monitor->total_size-heap.minimum_free_bytes;
    if(monitor->total_size)monitor->used_pct=100-(100*monitor->free_size/monitor->total_size);
    if(monitor->free_size)monitor->frag_pct=100-(100*monitor->free_biggest_size/monitor->free_size);
}
lv_result_t lv_mem_test_core(void)
{
    return heap_caps_check_integrity(GUI_CAPS,false)?LV_RESULT_OK:LV_RESULT_INVALID;
}
#endif
