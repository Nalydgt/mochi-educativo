idf_component_register(SRCS "main.c" "mochi.c" "mochi_animation.c" "coucou_motion.c" "mochi_appearance.c" "mochi_audio.c" "mochi_runtime.c" "mochi_controls.c" "mochi_gps.c" "mochi_vpn.c" "mochi_wifi_ui.c"
                           "mochi_options.c" "mochi_voice_policy.c" "mochi_wake.cpp" "mochi_resources.c" "mochi_dashboard.c" "mochi_motion_sensor.c" "mochi_power_ui.c"
                           "mochi_fonts.c" "mochi_latin_14.c" "mochi_latin_16.c" "mochi_latin_20.c" "mochi_navigation.c" "mochi_education.c" "mochi_lessons.c" "mochi_lesson_scene.c" "mochi_education_policy.c"
                       INCLUDE_DIRS "."
                       REQUIRES esp_timer esp_driver_gpio muse_display esp_wifi esp_event
                                esp_netif esp_http_client esp-tls nvs_flash lwip
                                esp_driver_usb_serial_jtag espressif__cjson microlink
                                mochi_microfrontend espressif__esp-tflite-micro spiffs app_update mbedtls)

# Native artwork is cropped at physical pixel size, without animation frames.
file(GLOB native_art CONFIGURE_DEPENDS "${CMAKE_CURRENT_LIST_DIR}/../assets/mochi-native/*.rgb565a8")
foreach(native_file IN LISTS native_art)
    get_filename_component(layer "${native_file}" NAME_WE)
    target_add_binary_data(${COMPONENT_LIB}
        "${native_file}" BINARY RENAME_TO "native_${layer}")
endforeach()
