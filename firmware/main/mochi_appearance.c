#include "mochi_appearance.h"
#include "mochi_runtime.h"
#include "nvs.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include <stdatomic.h>
#include <stdio.h>

static portMUX_TYPE lock=portMUX_INITIALIZER_UNLOCKED;
static mochi_appearance_t look={.motion=0};
static atomic_uint revision;
static int64_t changed_at;
static atomic_uint saved_revision;
static const char *const outfits[]={"none","partyHat","beanie","crown","sunglasses","roundGlasses","bow","scarf","witchHat","pumpkin","santaHat","bunnyEars"};
static const char *const clothes[]={"Sin ropa","Gorro de fiesta","Gorro de lana","Corona","Gafas de sol","Gafas redondas","Lazo","Bufanda","Sombrero de bruja","Calabaza","Gorro navideño","Orejas de conejo"};
static const char *const colours[]={"Original","Cielo","Lavanda","Rosa","Menta","Miel"};
static const char *const expressions[]={"Automática","Alegre","Cariñosa","Sorprendida","Orgullosa","Guiño","Bostezo","Traviesa"};
static const char *const motions[]={"Natural","Suave","Mínimo"};
static const unsigned counts[]={12,6,8,3};

static unsigned value(const mochi_appearance_t *p,unsigned field)
{
    return field==MOCHI_LOOK_OUTFIT?p->outfit:field==MOCHI_LOOK_COLOR?p->color:field==MOCHI_LOOK_EXPRESSION?p->expression:p->motion;
}
void mochi_appearance_init(void)
{
    nvs_handle_t h;
    if(nvs_open("mochi_look",NVS_READONLY,&h)==ESP_OK){
        mochi_appearance_t stored;size_t size=sizeof(stored);
        if(nvs_get_blob(h,"look",&stored,&size)==ESP_OK && size==sizeof(stored) && stored.outfit<12 && stored.color<6 && stored.expression<8 && stored.motion<3){portENTER_CRITICAL(&lock);look=stored;portEXIT_CRITICAL(&lock);}
        nvs_close(h);
    }
    saved_revision=atomic_fetch_add(&revision,1)+1;
}
void mochi_appearance_get(mochi_appearance_t *out)
{
    portENTER_CRITICAL(&lock);*out=look;portEXIT_CRITICAL(&lock);
}
bool mochi_appearance_set(unsigned field,unsigned next)
{
    if(field>3 || next>=counts[field])return false;
    portENTER_CRITICAL(&lock);
    unsigned old=value(&look,field);
    if(field==0)look.outfit=next;else if(field==1)look.color=next;else if(field==2)look.expression=next;else look.motion=next;
    if(old!=next){changed_at=esp_timer_get_time();atomic_fetch_add(&revision,1);}
    portEXIT_CRITICAL(&lock);
    return true;
}
void mochi_appearance_cycle(unsigned field,int direction)
{
    if(field>3)return;
    mochi_appearance_t p;mochi_appearance_get(&p);
    mochi_appearance_set(field,(value(&p,field)+counts[field]+(direction<0?-1:1))%counts[field]);
}
unsigned mochi_appearance_revision(void){return atomic_load(&revision);}
bool mochi_appearance_saved(void){return saved_revision==atomic_load(&revision);}
const char *mochi_appearance_outfit_id(unsigned index){return outfits[index<12?index:0];}
const char *mochi_appearance_label(unsigned field)
{
    mochi_appearance_t p;mochi_appearance_get(&p);
    return field==0?clothes[p.outfit]:field==1?colours[p.color]:field==2?expressions[p.expression]:motions[p.motion];
}
void mochi_appearance_poll(void)
{
    unsigned target=atomic_load(&revision);
    if(target==atomic_load(&saved_revision) || mochi_voice_busy())return;
    int64_t changed;
    portENTER_CRITICAL(&lock);changed=changed_at;portEXIT_CRITICAL(&lock);
    if(esp_timer_get_time()-changed<700000)return;
    mochi_appearance_flush();
}
bool mochi_appearance_flush(void)
{
    unsigned target;mochi_appearance_t p;
    portENTER_CRITICAL(&lock);p=look;target=atomic_load(&revision);portEXIT_CRITICAL(&lock);
    if(target==atomic_load(&saved_revision))return true;
    nvs_handle_t h;
    if(nvs_open("mochi_look",NVS_READWRITE,&h)!=ESP_OK)return false;
    esp_err_t result=nvs_set_blob(h,"look",&p,sizeof(p));
    if(result==ESP_OK)result=nvs_commit(h);
    nvs_close(h);
    if(result==ESP_OK)saved_revision=target;
    return result==ESP_OK;
}
