#pragma once
#include <stdbool.h>
#include <stdint.h>
typedef struct {
    bool storage,working,candidate;
    unsigned progress;
    char message[180];
    char update_message[180];
} mochi_resource_status_t;
void mochi_resources_start(void);
void mochi_resources_status(mochi_resource_status_t *out);
bool mochi_resources_prepare_name(const char *name);
bool mochi_resources_test_candidate(void);
bool mochi_resources_update(void);
bool mochi_resources_format(void);
void mochi_resources_diagnose(void);
