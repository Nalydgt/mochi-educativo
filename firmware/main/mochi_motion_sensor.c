/* QMI8658 register meanings follow the Waveshare QMI8658 example / SensorLib. */
#include "mochi_motion_sensor.h"
#include "bsp/esp-bsp.h"
#include "driver/i2c_master.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include <math.h>
static i2c_master_dev_handle_t imu;
static portMUX_TYPE lock=portMUX_INITIALIZER_UNLOCKED;
static bool ready,valid,lifted;
static float ax,ay,az;
static int64_t polled,moved,last_lift;
static esp_err_t write_reg(uint8_t reg,uint8_t value)
{
    uint8_t bytes[]={reg,value}; return i2c_master_transmit(imu,bytes,2,30);
}
void mochi_motion_sensor_init(void)
{
    i2c_device_config_t cfg={.dev_addr_length=I2C_ADDR_BIT_LEN_7,.device_address=0x6b,.scl_speed_hz=400000};
    uint8_t reg=0,id=0;
    if (i2c_master_bus_add_device(bsp_i2c_get_handle(),&cfg,&imu)!=ESP_OK ||
        i2c_master_transmit_receive(imu,&reg,1,&id,1,30)!=ESP_OK || id!=5) return;
    ready=write_reg(0x02,0x40)==ESP_OK && write_reg(0x03,0x08)==ESP_OK && write_reg(0x08,0x01)==ESP_OK;
}
void mochi_motion_sensor_poll(void)
{
    int64_t now=esp_timer_get_time();
    if (!ready || now-polled<40000) return;
    polled=now; uint8_t reg=0x35,bytes[6];
    if (i2c_master_transmit_receive(imu,&reg,1,bytes,6,30)!=ESP_OK) { portENTER_CRITICAL(&lock); valid=false; portEXIT_CRITICAL(&lock); return; }
    float x=(int16_t)(bytes[0]|bytes[1]<<8)/16384.f;
    float y=(int16_t)(bytes[2]|bytes[3]<<8)/16384.f;
    float z=(int16_t)(bytes[4]|bytes[5]<<8)/16384.f;
    portENTER_CRITICAL(&lock);
    float delta=fabsf(x-ax)+fabsf(y-ay)+fabsf(z-az);
    if (valid && delta>.45f) moved=now;
    if (moved && now-moved>300000 && now-moved<1000000 && delta<.04f && now-last_lift>8000000) {
        lifted=true; last_lift=now; moved=0;
    }
    if (!valid) { ax=x; ay=y; az=z; }
    else { ax=.7f*ax+.3f*x; ay=.7f*ay+.3f*y; az=.7f*az+.3f*z; }
    valid=true; portEXIT_CRITICAL(&lock);
}
bool mochi_motion_sensor_get(float *x,float *y,float *z)
{
    portENTER_CRITICAL(&lock); bool ok=valid; *x=ax; *y=ay; *z=az; portEXIT_CRITICAL(&lock); return ok;
}
bool mochi_motion_sensor_lifted(void)
{
    portENTER_CRITICAL(&lock); bool value=lifted; lifted=false; portEXIT_CRITICAL(&lock); return value;
}
