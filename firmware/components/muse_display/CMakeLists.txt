idf_component_register(SRCS "muse_lcd_bands.c" "mochi_display.c" "mochi_lv_memory.c"
                       INCLUDE_DIRS "."
                       REQUIRES esp_timer esp_driver_gpio esp_lcd
                                espressif__esp_lvgl_adapter
                                waveshare__esp32_s3_touch_amoled_1_75)
