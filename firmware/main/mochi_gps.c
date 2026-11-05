/* LC76G I2C protocol: Quectel LC26G(AB)&LC76G I2C Application Note,
 * and Waveshare's 09_LC76G_I2C example. Uses the existing shared BSP bus. */
#include "mochi_gps.h"
#include "mochi_controls.h"
#include "bsp/esp-bsp.h"
#include "driver/i2c_master.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "nvs.h"
#include <math.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <stdatomic.h>
static atomic_bool requested, tracking;
void mochi_gps_request(void) { atomic_store(&requested,true); }
void mochi_gps_tracking(bool enabled) { atomic_store(&tracking,enabled); if(enabled) mochi_gps_request(); }

static i2c_master_dev_handle_t command_dev, response_dev, write_dev;
static portMUX_TYPE state_lock = portMUX_INITIALIZER_UNLOCKED;
static mochi_gps_status_t state;
static int64_t last_fix_us, saved_at;
static int64_t restored_utc;
static char sentence[192];
static size_t sentence_used;
static uint8_t receive_buffer[512];
static uint32_t bytes_received, bytes_available;
static uint32_t polls;
static int64_t last_sentence_us;
static int last_error, last_stage;
static int configured, ack_id = -1, ack_result = -1;
typedef struct { uint32_t magic; double latitude, longitude; int64_t utc; } saved_location_t;
typedef struct { double latitude, longitude; bool valid, gga; int satellites; } parsed_fix_t;

static int hex(char c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    return -1;
}

static bool coordinate(const char *text, const char *hemisphere, bool latitude, double *out)
{
    if (!text[0] || strlen(hemisphere) != 1 || strspn(text, "0123456789.") != strlen(text)) return false;
    char *end;
    double raw = strtod(text, &end);
    double limit = latitude ? 90 : 180;
    if (*end || !isfinite(raw) || raw < 0 || raw > limit * 100) return false;
    int degrees = (int)(raw / 100);
    double minutes = raw - degrees * 100;
    double value = degrees + minutes / 60;
    if (minutes >= 60 || value > limit) return false;
    char direction = hemisphere[0];
    if (latitude ? (direction != 'N' && direction != 'S') : (direction != 'E' && direction != 'W')) return false;
    *out = direction == 'S' || direction == 'W' ? -value : value;
    return true;
}

static bool checksum_valid(const char *line)
{
    size_t length = strlen(line);
    if (length < 10 || length >= sizeof(sentence) || line[0] != '$') return false;
    const char *star = strchr(line, '*');
    if (!star || star - line != (ptrdiff_t)length - 3 || hex(star[1]) < 0 || hex(star[2]) < 0) return false;
    uint8_t checksum = 0;
    for (const char *c = line + 1; c < star; c++) checksum ^= (uint8_t)*c;
    return checksum == (hex(star[1]) << 4 | hex(star[2]));
}

static bool unsigned_field(const char *text,unsigned maximum,int *out)
{
    if(!text[0]) return false;
    unsigned value=0;
    for(const char *c=text;*c;c++) {
        if(*c<'0' || *c>'9') return false;
        value=value*10+(unsigned)(*c-'0');
        if(value>maximum) return false;
    }
    *out=(int)value; return true;
}

static bool parse_sentence(const char *line, parsed_fix_t *out)
{
    if (!checksum_valid(line)) return false;
    const char *star = strchr(line, '*');
    char copy[192];
    memcpy(copy, line + 1, star - line - 1);
    copy[star - line - 1] = 0;
    char *fields[24] = {copy};
    size_t count = 1;
    for (char *c = copy; *c; c++) if (*c == ',') {
        *c = 0;
        if (count == 24) return false;
        fields[count++] = c + 1;
    }
    memset(out, 0, sizeof(*out));
    if (strlen(fields[0]) != 5) return false;
    if (!strcmp(fields[0] + 2, "RMC") && count >= 7) {
        if (strcmp(fields[2], "A")) return !strcmp(fields[2], "V");
        out->valid = coordinate(fields[3], fields[4], true, &out->latitude) &&
                     coordinate(fields[5], fields[6], false, &out->longitude);
        return out->valid;
    }
    if (!strcmp(fields[0] + 2, "GGA") && count >= 9) {
        out->gga = true;
        int quality;
        if (!unsigned_field(fields[7],99,&out->satellites) || !unsigned_field(fields[6],5,&quality)) return false;
        if (!quality) return true;
        if (fields[8][0]) {
            char *end;
            double dilution=strtod(fields[8],&end);
            if (*end || !isfinite(dilution) || dilution<0 || dilution>20) return false;
        }
        out->valid = coordinate(fields[2], fields[3], true, &out->latitude) &&
                     coordinate(fields[4], fields[5], false, &out->longitude);
        return out->valid;
    }
    return false;
}

void mochi_gps_status(mochi_gps_status_t *out)
{
    int64_t received, utc;
    portENTER_CRITICAL(&state_lock);
    *out = state;
    received = last_fix_us;
    utc = restored_utc;
    portEXIT_CRITICAL(&state_lock);
    int64_t age = received ? (esp_timer_get_time() - received) / 1000000 :
        (utc && time(NULL) > 1700000000 ? (int64_t)time(NULL) - utc : -1);
    out->age_seconds = age >= 0 && age < INT32_MAX ? (int)age : -1;
    out->available = out->age_seconds >= 0 && out->age_seconds <= 86400;
    out->fix = out->fix && received && age >= 0 && age < 15;
}

static void save_position(void)
{
    int64_t now = esp_timer_get_time();
    if (saved_at && now - saved_at < 600000000) return;
    mochi_gps_status_t location;
    mochi_gps_status(&location);
    time_t utc = time(NULL);
    if (!location.fix || utc < 1700000000) return;
    saved_location_t record = {.magic = 0x4d475001, .latitude = location.latitude,
                              .longitude = location.longitude, .utc = utc};
    nvs_handle_t handle;
    if (nvs_open("mochi_gps", NVS_READWRITE, &handle) != ESP_OK) return;
    esp_err_t result = nvs_set_blob(handle, "last", &record, sizeof(record));
    if (result == ESP_OK) result = nvs_commit(handle);
    nvs_close(handle);
    if (result == ESP_OK) saved_at = now;
}

static void consume(const uint8_t *bytes, size_t length)
{
    for (size_t i = 0; i < length; i++) {
        char c = (char)bytes[i];
        if (c == '$') sentence_used = 0;
        if (!sentence_used && c != '$') continue;
        if (c == '\r') continue;
        if (c == '\n') {
            sentence[sentence_used] = 0;
            int command, result;
            if (!strncmp(sentence, "$PAIR001,", 9) && checksum_valid(sentence) &&
                sscanf(sentence + 9, "%d,%d", &command, &result) == 2) {
                portENTER_CRITICAL(&state_lock);
                ack_id = command;
                ack_result = result;
                portEXIT_CRITICAL(&state_lock);
            }
            parsed_fix_t fix;
            if (parse_sentence(sentence, &fix)) {
                portENTER_CRITICAL(&state_lock);
                state.sentences++;
                last_sentence_us = esp_timer_get_time();
                if (fix.gga) state.satellites = fix.satellites;
                state.fix = fix.valid;
                if (fix.valid) {
                    state.latitude = fix.latitude;
                    state.longitude = fix.longitude;
                    last_fix_us = esp_timer_get_time();
                }
                portEXIT_CRITICAL(&state_lock);
            }
            sentence_used = 0;
        } else if (sentence_used + 1 < sizeof(sentence)) sentence[sentence_used++] = c;
        else sentence_used = 0;
    }
}

static bool send_pair(const char *body)
{
    char message[64];
    uint8_t checksum = 0;
    for (const char *c = body; *c; c++) checksum ^= *c;
    int length = snprintf(message, sizeof(message), "$%s*%02X\r\n", body, checksum);
    if (length <= 0 || length >= sizeof(message)) return false;
    const uint8_t free_command[] = {4,0,0x51,0xaa,4,0,0,0};
    uint8_t available[4];
    vTaskDelay(pdMS_TO_TICKS(20));
    if (i2c_master_transmit(command_dev, free_command, 8, 100) != ESP_OK) return false;
    vTaskDelay(pdMS_TO_TICKS(20));
    if (i2c_master_receive(response_dev, available, 4, 100) != ESP_OK) return false;
    uint32_t free_bytes = (uint32_t)available[0] | (uint32_t)available[1] << 8 |
        (uint32_t)available[2] << 16 | (uint32_t)available[3] << 24;
    if (free_bytes < (uint32_t)length) return false;
    uint8_t command[] = {0,0x10,0x53,0xaa,(uint8_t)length,0,0,0};
    vTaskDelay(pdMS_TO_TICKS(20));
    if (i2c_master_transmit(command_dev, command, 8, 100) != ESP_OK) return false;
    vTaskDelay(pdMS_TO_TICKS(20));
    bool ok = i2c_master_transmit(write_dev, (uint8_t *)message, length, 100) == ESP_OK;
    vTaskDelay(pdMS_TO_TICKS(20));
    return ok;
}

static void reader(void *argument)
{
    (void)argument;
    const uint8_t length_command[] = {0x08,0x00,0x51,0xaa,0x04,0,0,0};
    const char *initialization[] = {"PAIR002", "PAIR062,0,1", "PAIR062,4,1"};
    int64_t next_configuration = 0;
    bool running=false,standby=false;
    int64_t deadline=0;
    while (true) {
        vTaskDelay(pdMS_TO_TICKS(80));
        if (atomic_exchange(&requested,false)) {
            if(!running) { configured=0; next_configuration=0; standby=false; }
            running=true; deadline=esp_timer_get_time()+90000000;
        }
        if (!running) {
            if (!standby) standby=send_pair("PAIR003");
            vTaskDelay(pdMS_TO_TICKS(500)); continue;
        }
        mochi_gps_status_t latest; mochi_gps_status(&latest);
        if (!atomic_load(&tracking) && ((latest.fix && latest.age_seconds<2 && configured>=3) || esp_timer_get_time()>deadline)) {
            save_position(); standby=send_pair("PAIR003"); running=false; continue;
        }
        portENTER_CRITICAL(&state_lock);
        polls++;
        portEXIT_CRITICAL(&state_lock);
        if (mochi_controls_power_pending()) continue;
        int stage = 1;
        uint8_t length_bytes[4];
        esp_err_t error = i2c_master_transmit(command_dev, length_command, 8, 100);
        if (error == ESP_OK) {
            stage = 2;
            vTaskDelay(pdMS_TO_TICKS(20));
            error = i2c_master_receive(response_dev, length_bytes, 4, 100);
        }
        if (error == ESP_OK) {
            portENTER_CRITICAL(&state_lock);
            state.detected = true;
            portEXIT_CRITICAL(&state_lock);
            if (configured < 3 && esp_timer_get_time() >= next_configuration) {
                bool sent = send_pair(initialization[configured]);
                if (sent) {
                    portENTER_CRITICAL(&state_lock);
                    configured++;
                    portEXIT_CRITICAL(&state_lock);
                } else next_configuration = esp_timer_get_time() + 10000000;
                continue; /* Query a new length after command acknowledgements. */
            }
            uint32_t count = (uint32_t)length_bytes[0] | (uint32_t)length_bytes[1] << 8 |
                (uint32_t)length_bytes[2] << 16 | (uint32_t)length_bytes[3] << 24;
            portENTER_CRITICAL(&state_lock);
            bytes_available = count;
            portEXIT_CRITICAL(&state_lock);
            if (!count) { save_position(); continue; }
            if (count > sizeof(receive_buffer)) count = sizeof(receive_buffer);
            uint8_t read_command[] = {0,0x20,0x51,0xaa, count & 255, (count >> 8) & 255, 0,0};
            /* The module needs >=10 ms BETWEEN transactions, also after
             * receiving the length and before sending the next command. */
            vTaskDelay(pdMS_TO_TICKS(20));
            stage = 3;
            error = i2c_master_transmit(command_dev, read_command, 8, 100);
            if (error == ESP_OK) {
                stage = 4;
                vTaskDelay(pdMS_TO_TICKS(20));
                error = i2c_master_receive(response_dev, receive_buffer, count, 150);
                if (error == ESP_OK) {
                    consume(receive_buffer, count);
                    portENTER_CRITICAL(&state_lock);
                    bytes_received += count;
                    last_error = last_stage = 0;
                    portEXIT_CRITICAL(&state_lock);
                }
            }
        }
        if (error != ESP_OK) {
            portENTER_CRITICAL(&state_lock);
            state.errors++;
            state.fix = false;
            last_error = error;
            last_stage = stage;
            portEXIT_CRITICAL(&state_lock);
            vTaskDelay(pdMS_TO_TICKS(1500));
        }
        save_position();
    }
}

void mochi_gps_start(void)
{
    nvs_handle_t handle;
    saved_location_t record;
    size_t size = sizeof(record);
    if (nvs_open("mochi_gps", NVS_READONLY, &handle) == ESP_OK) {
        if (nvs_get_blob(handle, "last", &record, &size) == ESP_OK && size == sizeof(record) &&
            record.magic == 0x4d475001 && isfinite(record.latitude) && isfinite(record.longitude) &&
            fabs(record.latitude) <= 90 && fabs(record.longitude) <= 180 && record.utc > 1700000000) {
            state.latitude = record.latitude;
            state.longitude = record.longitude;
            restored_utc = record.utc;
        }
        nvs_close(handle);
    }
    i2c_device_config_t config = {.dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = 0x50, .scl_speed_hz = 400000};
    if (i2c_master_bus_add_device(bsp_i2c_get_handle(), &config, &command_dev) != ESP_OK) return;
    config.device_address = 0x54;
    if (i2c_master_bus_add_device(bsp_i2c_get_handle(), &config, &response_dev) != ESP_OK) return;
    config.device_address = 0x58;
    if (i2c_master_bus_add_device(bsp_i2c_get_handle(), &config, &write_dev) != ESP_OK) return;
    if (xTaskCreatePinnedToCore(reader, "mochi_gps", 4096, NULL, 1, NULL, 0) == pdPASS)
        ESP_LOGI("mochi_gps", "LC76G ready; position search on demand");
}

void mochi_gps_diagnose(void)
{
    mochi_gps_status_t gps;
    mochi_gps_status(&gps);
    portENTER_CRITICAL(&state_lock);
    uint32_t received = bytes_received, available = bytes_available;
    uint32_t iterations = polls;
    int sentence_age = last_sentence_us ? (int)((esp_timer_get_time() - last_sentence_us) / 1000000) : -1;
    int error = last_error, stage = last_stage;
    int commands_sent = configured, command_ack = ack_id, result_ack = ack_result;
    portEXIT_CRITICAL(&state_lock);
    printf("@mochi_gps detected=%d fix=%d available=%d satellites=%d age=%d sentences=%lu errors=%lu bytes=%lu pending=%lu error=%d stage=%d polls=%lu nmea_age=%d config=%d ack=%d:%d\n",
        gps.detected, gps.fix, gps.available, gps.satellites, gps.age_seconds,
        (unsigned long)gps.sentences, (unsigned long)gps.errors, (unsigned long)received, (unsigned long)available, error, stage,
        (unsigned long)iterations, sentence_age, commands_sent, command_ack, result_ack);
    fflush(stdout);
}

bool mochi_gps_self_test(void)
{
    parsed_fix_t value;
    double coordinate_value;
    int field_value;
    return parse_sentence("$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A", &value) &&
        value.valid && fabs(value.latitude - 48.1173) < .00001 && fabs(value.longitude - 11.5166667) < .00001 &&
        !parse_sentence("$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6B", &value) &&
        parse_sentence("$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47", &value) &&
        value.valid && value.satellites == 8 &&
        unsigned_field("08",99,&field_value) && field_value==8 &&
        !unsigned_field("8x",99,&field_value) && !unsigned_field("",99,&field_value) &&
        !unsigned_field("-1",99,&field_value) && !unsigned_field("100",99,&field_value) &&
        !parse_sentence("$GPGGA,123519,4807.038,N,01131.000,E,1,08,nan,545.4,M,46.9,M,,*01", &value) &&
        !parse_sentence("$GPGGA,123519,4807.038,N,01131.000,E,1x,08,0.9,545.4,M,46.9,M,,*3F", &value) &&
        coordinate("03430.0", "W", false, &coordinate_value) && fabs(coordinate_value + 34.5) < .00001 &&
        !coordinate("1260.0", "N", true, &coordinate_value) && !coordinate("9100.0", "N", true, &coordinate_value);
}
