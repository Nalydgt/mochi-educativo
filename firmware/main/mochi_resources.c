#include "mochi_resources.h"
#include "mochi_options.h"
#include "mochi_appearance.h"
#include "mochi_runtime.h"
#include "mochi.h"
#include "mochi_animation.h"
#include "cJSON.h"
#include "esp_heap_caps.h"
#include "esp_lv_adapter.h"
#include "esp_ota_ops.h"
#include "esp_app_desc.h"
#include "esp_spiffs.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "mbedtls/base64.h"
#include "mbedtls/md.h"
#include "mbedtls/pk.h"
#include <math.h>
#include <stdatomic.h>
#include <stdio.h>
#include <string.h>

static portMUX_TYPE lock=portMUX_INITIALIZER_UNLOCKED;
static mochi_resource_status_t status;
static atomic_int request;
static char requested_name[97];
static TaskHandle_t task;
static struct { char name[97],id[33]; float cutoff; unsigned window,arena,slot; } candidate;
typedef struct { uint8_t *bytes; size_t used,capacity; } blob_t;

static void message(const char *text,unsigned progress,bool working)
{
    portENTER_CRITICAL(&lock);
    strlcpy(status.message,text,sizeof(status.message)); status.progress=progress; status.working=working;
    portEXIT_CRITICAL(&lock);
}
static void update_message(const char *text,unsigned progress,bool working)
{
    portENTER_CRITICAL(&lock);
    strlcpy(status.message,text,sizeof(status.message));
    strlcpy(status.update_message,text,sizeof(status.update_message));
    status.progress=progress; status.working=working;
    portEXIT_CRITICAL(&lock);
}
void mochi_resources_status(mochi_resource_status_t *out)
{
    portENTER_CRITICAL(&lock); *out=status; portEXIT_CRITICAL(&lock);
}
static esp_err_t append(const uint8_t *bytes,size_t size,void *context)
{
    blob_t *blob=context;
    if (blob->used+size>=blob->capacity) return ESP_ERR_INVALID_SIZE;
    memcpy(blob->bytes+blob->used,bytes,size); blob->used+=size; blob->bytes[blob->used]=0; return ESP_OK;
}
static cJSON *fetch_json_status(const char *route,const char *body,int *http)
{
    if (http) *http=0;
    blob_t blob={.capacity=12288}; blob.bytes=heap_caps_malloc(blob.capacity,MALLOC_CAP_SPIRAM);
    if (!blob.bytes) return NULL;
    esp_err_t result=mochi_runtime_request_with_timeout(route,body,append,&blob,blob.capacity-1,http,10000);
    cJSON *json=result==ESP_OK ? cJSON_ParseWithLength((char *)blob.bytes,blob.used) : NULL;
    free(blob.bytes); return json;
}
static cJSON *fetch_json(const char *route,const char *body)
{
    return fetch_json_status(route,body,NULL);
}
static const char *text(cJSON *json,const char *key)
{
    cJSON *item=cJSON_GetObjectItemCaseSensitive(json,key); return cJSON_IsString(item)?item->valuestring:NULL;
}
static bool identifier(const char *value)
{
    return value && strlen(value)==32 && strspn(value,"0123456789abcdef")==32;
}
static bool bootstrap_key(void)
{
    mochi_options_t options; mochi_options_get(&options);
    if (options.public_key[0]) return true;
    /* First trust is established only through the pinned WireGuard peer or HTTPS. */
    if (!mochi_runtime_trusted_channel()) return false;
    cJSON *json=fetch_json("/v1/artifacts/public-key",NULL);
    const char *key=text(json,"der"); bool ok=key && strlen(key)<sizeof(options.public_key);
    if (ok) { strlcpy(options.public_key,key,sizeof(options.public_key)); ok=mochi_options_set(&options) && mochi_options_flush(); mochi_appearance_flush(); }
    cJSON_Delete(json); return ok;
}
static cJSON *verified_payload(cJSON *envelope)
{
    const char *encoded=text(envelope,"payload"),*signature=text(envelope,"signature"),*algorithm=text(envelope,"algorithm");
    if (!encoded || !signature || !algorithm || strcmp(algorithm,"ecdsa-p256-sha256") || strlen(encoded)>11000 || strlen(signature)>200) return NULL;
    mochi_options_t options; mochi_options_get(&options);
    uint8_t key[128],sig[128],digest[32]; size_t key_size=0,sig_size=0,payload_size=0;
    uint8_t *payload=heap_caps_malloc(8193,MALLOC_CAP_SPIRAM);
    if (!payload) return NULL;
    bool ok=mbedtls_base64_decode(key,sizeof(key),&key_size,(const unsigned char *)options.public_key,strlen(options.public_key))==0 &&
        mbedtls_base64_decode(sig,sizeof(sig),&sig_size,(const unsigned char *)signature,strlen(signature))==0 &&
        mbedtls_base64_decode(payload,8192,&payload_size,(const unsigned char *)encoded,strlen(encoded))==0;
    mbedtls_pk_context pk; mbedtls_pk_init(&pk);
    if (ok) ok=mbedtls_pk_parse_public_key(&pk,key,key_size)==0 &&
        mbedtls_pk_get_bitlen(&pk)==256 && mbedtls_md(mbedtls_md_info_from_type(MBEDTLS_MD_SHA256),payload,payload_size,digest)==0 &&
        mbedtls_pk_verify(&pk,MBEDTLS_MD_SHA256,digest,sizeof(digest),sig,sig_size)==0;
    cJSON *result=ok ? cJSON_ParseWithLength((char *)payload,payload_size) : NULL;
    mbedtls_pk_free(&pk); free(payload);
    const char *target=text(result,"target"),*idf=text(result,"idf");
    if (!target || strcmp(target,"esp32s3") || !idf || strcmp(idf,"6.0.1")) { cJSON_Delete(result); return NULL; }
    return result;
}
typedef struct {
    FILE *file;
    esp_ota_handle_t ota;
    mbedtls_md_context_t hash;
    size_t received,expected;
} download_t;
static esp_err_t save_chunk(const uint8_t *bytes,size_t size,void *context)
{
    download_t *out=context;
    if (out->received+size>out->expected) return ESP_ERR_INVALID_SIZE;
    esp_err_t result=out->file ? (fwrite(bytes,1,size,out->file)==size?ESP_OK:ESP_FAIL) : esp_ota_write(out->ota,bytes,size);
    if (result!=ESP_OK || mbedtls_md_update(&out->hash,bytes,size)!=0) return ESP_FAIL;
    out->received+=size; return ESP_OK;
}
static bool download(const char *route,cJSON *manifest,FILE *file,esp_ota_handle_t ota)
{
    const char *expected=text(manifest,"sha256");
    cJSON *size=cJSON_GetObjectItemCaseSensitive(manifest,"size");
    if (!expected || strlen(expected)!=64 || strspn(expected,"0123456789abcdef")!=64 || !cJSON_IsNumber(size) || size->valuedouble<16 || size->valuedouble>4194304) return false;
    download_t out={.file=file,.ota=ota,.expected=(size_t)size->valuedouble};
    mbedtls_md_init(&out.hash); uint8_t digest[32]; char hex[65];
    bool ok=mbedtls_md_setup(&out.hash,mbedtls_md_info_from_type(MBEDTLS_MD_SHA256),0)==0 && mbedtls_md_starts(&out.hash)==0;
    if (ok) ok=mochi_runtime_request(route,NULL,save_chunk,&out,out.expected,NULL)==ESP_OK && out.received==out.expected && mbedtls_md_finish(&out.hash,digest)==0;
    if (ok) { for (int i=0;i<32;i++) snprintf(hex+i*2,3,"%02x",digest[i]); ok=!strcmp(hex,expected); }
    mbedtls_md_free(&out.hash); return ok;
}
static bool mount_storage(bool format)
{
    esp_vfs_spiffs_conf_t config={.base_path="/mochi",.partition_label="storage",.max_files=3,.format_if_mount_failed=format};
    if (status.storage) return true;
    bool ok=esp_vfs_spiffs_register(&config)==ESP_OK;
    portENTER_CRITICAL(&lock); status.storage=ok; portEXIT_CRITICAL(&lock); return ok;
}
bool mochi_resources_format(void) { return !status.working && mount_storage(true); }

static void poll_job(void)
{
    mochi_options_t options; mochi_options_get(&options);
    if (!options.pending_id[0] || mochi_voice_busy() || !identifier(options.pending_id)) return;
    char route[140]; snprintf(route,sizeof(route),"/v1/wake-model/jobs/%s",options.pending_id);
    cJSON *json=fetch_json(route,NULL);
    const char *stage=text(json,"stage");
    if (!stage) { cJSON_Delete(json); message("Preparacion pendiente; comprueba el servidor",0,false); return; }
    cJSON *percent=cJSON_GetObjectItemCaseSensitive(json,"progress");
    unsigned progress=cJSON_IsNumber(percent) && percent->valueint>=0 && percent->valueint<=100?percent->valueint:0;
    const char *notice=!strcmp(stage,"queued")?"Nuevo nombre en cola":!strcmp(stage,"preparing")?"Preparando ejemplos":
        !strcmp(stage,"training")?"Entrenando el nuevo nombre":!strcmp(stage,"checking")?"Comprobando reconocimiento":"Preparacion pendiente";
    message(notice,progress,false);
    if (!strcmp(stage,"failed")) {
        options.pending_id[0]=0; options.pending_name[0]=0; mochi_options_set(&options);
        const char *reason=text(json,"error");
        message(reason && !strcmp(reason,"training_quality_not_met")?
            (options.model_id[0]?"Reconocimiento insuficiente. Conservamos el nombre anterior":
                "Reconocimiento insuficiente. Aun no escucho por nombre"):
            (options.model_id[0]?"Fallo del preparador. Seguimos con el anterior":
                "Fallo del preparador. Aun no escucho por nombre"),0,false);
    } else if (!strcmp(stage,"ready") && !status.candidate && status.storage && bootstrap_key()) {
        cJSON_Delete(json); json=NULL;
        snprintf(route,sizeof(route),"/v1/wake-models/%s/manifest",options.pending_id);
        cJSON *envelope=fetch_json(route,NULL),*payload=verified_payload(envelope);
        const char *kind=text(payload,"kind"),*name=text(payload,"name"),*frontend=text(payload,"frontend");
        cJSON *cutoff=cJSON_GetObjectItemCaseSensitive(payload,"probability_cutoff"),*window=cJSON_GetObjectItemCaseSensitive(payload,"sliding_window"),*arena=cJSON_GetObjectItemCaseSensitive(payload,"arena_bytes");
        bool valid=kind && !strcmp(kind,"wake-model") && name && !strcmp(name,options.pending_name) && strlen(name)<sizeof(candidate.name) &&
            frontend && !strcmp(frontend,"microfrontend-v1") && cJSON_IsNumber(cutoff) && cutoff->valuedouble>0 && cutoff->valuedouble<=1 &&
            cJSON_IsNumber(window) && window->valueint>0 && window->valueint<=16 && cJSON_IsNumber(arena) && arena->valueint>=32768 && arena->valueint<=1048576;
        if (valid) {
            candidate.slot=1-options.slot; char path[40]; snprintf(path,sizeof(path),"/mochi/wake%u.tflite",candidate.slot);
            FILE *file=fopen(path,"wb");
            message("Descargando modelo firmado",95,true);
            snprintf(route,sizeof(route),"/v1/wake-models/%s/model",options.pending_id);
            valid=file && download(route,payload,file,0);
            if (file) { if (fflush(file)) valid=false; fclose(file); }
            if (valid) {
                strlcpy(candidate.id,options.pending_id,sizeof(candidate.id)); strlcpy(candidate.name,name,sizeof(candidate.name));
                candidate.cutoff=cutoff->valuedouble; candidate.window=window->valueint; candidate.arena=arena->valueint;
                portENTER_CRITICAL(&lock); status.candidate=true; portEXIT_CRITICAL(&lock);
                message("Modelo listo. Pulsa Probar nombre",100,false);
            } else { remove(path); message("Descarga incompleta. Se mantiene el nombre actual",0,false); }
        } else message("El manifiesto no es valido. Se mantiene el nombre actual",0,false);
        cJSON_Delete(payload); cJSON_Delete(envelope);
    }
    cJSON_Delete(json);
}
static void perform_update(void)
{
    const esp_partition_t *partition=esp_ota_get_next_update_partition(NULL);
    if (!partition) { update_message("Necesita la migracion inicial por USB",0,false); return; }
    if (!bootstrap_key()) { update_message("No se pudo verificar el servidor. Reintenta",0,false); return; }
    int http=0;
    cJSON *envelope=fetch_json_status("/v1/updates/manifest",NULL,&http);
    if (!envelope) {
        update_message(http==404?"No hay actualizaciones publicadas":
            (http==401 || http==403)?"El servidor rechazó el acceso. Revisa la configuración":
            http==200?"Respuesta de actualización no válida. Reintenta":
            "Sin conexión al servidor. Revisa el Wi-Fi y reintenta",0,false);
        return;
    }
    cJSON *payload=verified_payload(envelope);
    const char *kind=text(payload,"kind"),*version=text(payload,"version");
    cJSON *size=cJSON_GetObjectItemCaseSensitive(payload,"size");
    bool valid=kind && !strcmp(kind,"firmware") && version && strlen(version)<=31 &&
        cJSON_IsNumber(size) && size->valuedouble>0 && size->valuedouble<=partition->size;
    if (!valid) {
        cJSON_Delete(payload); cJSON_Delete(envelope);
        update_message("Actualización no válida. Se conserva la versión actual",0,false); return;
    }
    if (!strcmp(version,esp_app_get_description()->version)) {
        cJSON_Delete(payload); cJSON_Delete(envelope);
        update_message("Mochi está actualizado",100,false); return;
    }
    update_message("Descargando actualización",0,true);
    esp_ota_handle_t handle=0;
    bool ok=esp_ota_begin(partition,size->valuedouble,&handle)==ESP_OK;
    if (ok) ok=download("/v1/updates/firmware",payload,NULL,handle);
    if (!ok && handle) esp_ota_abort(handle);
    if (ok) ok=esp_ota_end(handle)==ESP_OK;
    if (ok) ok=esp_ota_set_boot_partition(partition)==ESP_OK;
    cJSON_Delete(payload); cJSON_Delete(envelope);
    if (ok) { mochi_options_flush(); mochi_appearance_flush(); update_message("Actualizacion verificada. Reiniciando",100,true); vTaskDelay(pdMS_TO_TICKS(1000)); esp_restart(); }
    update_message("No se instaló. Se conserva la versión actual",0,false);
}
static void worker(void *argument)
{
    (void)argument; if (mount_storage(false)) mochi_animation_cleanup_storage();
    message(status.storage?"Voz por nombre aun sin modelo":"Almacenamiento pendiente de preparar por USB",0,false);
    while (true) {
        if (mochi_animation_uploading()) { vTaskDelay(pdMS_TO_TICKS(100)); continue; }
        static bool initial_requested=false;
        mochi_options_t current; mochi_options_get(&current);
        if (!initial_requested && status.storage && !current.model_id[0] && !current.pending_id[0] && mochi_runtime_trusted_channel()) {
            initial_requested=mochi_resources_prepare_name(current.name);
        }
        int action=atomic_exchange(&request,0);
        if (action==1) {
            mochi_options_t options; mochi_options_get(&options);
            if (!status.storage) message("Prepara primero el almacenamiento por USB",0,false);
            else {
                cJSON *body=cJSON_CreateObject(); cJSON_AddStringToObject(body,"name",requested_name);
                cJSON_AddStringToObject(body,"device_id",mochi_runtime_device_id());
                char *encoded=cJSON_PrintUnformatted(body);
                cJSON *response=encoded?fetch_json("/v1/wake-model/jobs",encoded):NULL;
                const char *id=text(response,"id");
                if (identifier(id)) {
                    strlcpy(options.pending_id,id,sizeof(options.pending_id)); strlcpy(options.pending_name,requested_name,sizeof(options.pending_name));
                    mochi_options_set(&options); mochi_options_flush(); mochi_appearance_flush(); message("Nombre en preparacion. El anterior sigue activo",0,false);
                } else message("No se pudo iniciar. Comprueba servidor y preparador",0,false);
                cJSON_free(encoded); cJSON_Delete(body); cJSON_Delete(response);
            }
        } else if (action==2 && status.candidate) {
            char path[40]; snprintf(path,sizeof(path),"/mochi/wake%u.tflite",candidate.slot);
            if (mochi_voice_test_wake_start(path,candidate.cutoff,candidate.window,candidate.arena)) {
                message("Prueba en marcha: sigue las instrucciones",100,true);
                while (!mochi_voice_test_wake_result()) vTaskDelay(pdMS_TO_TICKS(100));
                if (mochi_voice_test_wake_result()>0) {
                    mochi_options_t options; mochi_options_get(&options);
                    mochi_options_t previous=options;
                    strlcpy(options.name,candidate.name,sizeof(options.name)); strlcpy(options.model_id,candidate.id,sizeof(options.model_id));
                    options.slot=candidate.slot; options.cutoff=candidate.cutoff; options.window=candidate.window; options.arena_bytes=candidate.arena;
                    options.pending_id[0]=0; options.pending_name[0]=0;
                    if (mochi_options_set(&options) && mochi_options_flush()) {
                        mochi_voice_reload_model();
                        portENTER_CRITICAL(&lock); status.candidate=false; portEXIT_CRITICAL(&lock);
                        message("Nuevo nombre activado",100,false);
                    } else {
                        mochi_options_set(&previous); mochi_options_flush(); mochi_appearance_flush();
                        message("No se pudo guardar. Seguimos con el nombre anterior",100,false);
                    }
                } else message("Prueba no superada. Seguimos con el nombre anterior",100,false);
            } else message("Espera a terminar la conversacion y repite la prueba",100,false);
        } else if (action==3) perform_update();
        if (!status.working) poll_job();
        vTaskDelay(pdMS_TO_TICKS(3000));
    }
}
void mochi_resources_start(void)
{
    /* Flash/NVS/OTA temporarily disable the PSRAM cache. Their caller must
     * execute with an internal stack, even when downloads live in PSRAM. */
    if (xTaskCreatePinnedToCore(worker,"mochi_resources",8192,NULL,1,&task,0)!=pdPASS)
        message("Preparacion de recursos no disponible",0,false);
}
bool mochi_resources_prepare_name(const char *name)
{
    mochi_options_t options; mochi_options_get(&options);
    if (!task || mochi_animation_uploading() || !name || !name[0] || strlen(name)>=sizeof(requested_name) || options.pending_id[0] || status.working || atomic_load(&request)) return false;
    strlcpy(requested_name,name,sizeof(requested_name)); message("Contactando con el preparador",0,true); atomic_store(&request,1); return true;
}
bool mochi_resources_test_candidate(void)
{
    if (!task || mochi_animation_uploading() || !status.candidate || status.working || atomic_load(&request)) return false;
    atomic_store(&request,2); return true;
}
bool mochi_resources_update(void)
{
    if (!task || mochi_animation_uploading() || status.working || atomic_load(&request) || mochi_voice_busy()) return false;
    update_message("Comprobando actualizaciones",0,true); atomic_store(&request,3); return true;
}
void mochi_resources_diagnose(void)
{
    mochi_resource_status_t snapshot; mochi_resources_status(&snapshot);
    printf("@mochi_resources storage=%d working=%d candidate=%d progress=%u stack_free=%u\n",snapshot.storage,snapshot.working,snapshot.candidate,snapshot.progress,task?(unsigned)uxTaskGetStackHighWaterMark(task):0); fflush(stdout);
}
