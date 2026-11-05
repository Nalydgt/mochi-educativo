# esp_codec_dev 1.5.11 ignores I2S format/allocation errors in open(), then
# enables a channel with missing DMA buffers. Keep managed sources untouched;
# compile a checked copy and fail configuration if the upstream code changes.
idf_component_get_property(codec_dir espressif__esp_codec_dev COMPONENT_DIR)
idf_component_get_property(codec_target espressif__esp_codec_dev COMPONENT_LIB)
file(READ "${codec_dir}/esp_codec_dev.c" codec_source)
string(REPLACE "\r\n" "\n" codec_source "${codec_source}")
set(unchecked [=[    if (data_if->set_fmt) {
        data_if->set_fmt(data_if, dev->dev_caps, fs);
    }
    if (data_if->enable) {
        data_if->enable(data_if, dev->dev_caps, true);
    }]=])
set(checked [=[    int data_ret = ESP_CODEC_DEV_OK;
    if (data_if->set_fmt) {
        data_ret = data_if->set_fmt(data_if, dev->dev_caps, fs);
    }
    if (data_ret == ESP_CODEC_DEV_OK && data_if->enable) {
        data_ret = data_if->enable(data_if, dev->dev_caps, true);
    }
    if (data_ret != ESP_CODEC_DEV_OK) {
        dev->input_opened = dev->output_opened = false;
        ESP_LOGE(TAG, "Data interface initialization failed: %d", data_ret);
        return data_ret;
    }]=])
string(FIND "${codec_source}" "${unchecked}" patch_position)
if(patch_position EQUAL -1)
    message(FATAL_ERROR "esp_codec_dev open() changed; review checked_codec.cmake")
endif()
string(REPLACE "${unchecked}" "${checked}" codec_source "${codec_source}")
set(codec_checked "${CMAKE_BINARY_DIR}/mochi_esp_codec_dev_checked.c")
file(WRITE "${codec_checked}" "${codec_source}")
get_target_property(codec_sources ${codec_target} SOURCES)
set(original_found FALSE)
foreach(codec_file IN LISTS codec_sources)
    get_filename_component(codec_name "${codec_file}" NAME)
    if(codec_name STREQUAL "esp_codec_dev.c")
        list(REMOVE_ITEM codec_sources "${codec_file}")
        set(original_found TRUE)
    endif()
endforeach()
if(NOT original_found)
    message(FATAL_ERROR "Cannot locate original esp_codec_dev.c in codec target")
endif()
set_property(TARGET ${codec_target} PROPERTY SOURCES "${codec_sources}")
target_sources(${codec_target} PRIVATE "${codec_checked}")
target_include_directories(${codec_target} PRIVATE "${codec_dir}")
