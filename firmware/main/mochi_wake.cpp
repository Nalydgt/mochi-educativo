#include "mochi_wake.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/micro/micro_resource_variable.h"
#include "tensorflow/lite/schema/schema_generated.h"
#include "tensorflow/lite/experimental/microfrontend/lib/frontend.h"
#include "tensorflow/lite/experimental/microfrontend/lib/frontend_util.h"
#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <new>

namespace {
uint8_t *model_bytes, *arena;
tflite::MicroInterpreter *interpreter;
tflite::MicroResourceVariables *variables;
FrontendState frontend{};
bool frontend_initialized;
std::atomic_bool ready{false};
std::atomic_uint inferences{0}, failures{0}, detections{0}, peak_us{0};
unsigned slices, filled, probability_window=5, probability_count, probability_pos;
unsigned warmed_slices;
constexpr unsigned kWarmupSlices=150;
float cutoff=.9f, history[16];
std::atomic<float> probability{0};
alignas(tflite::MicroInterpreter) uint8_t interpreter_storage[sizeof(tflite::MicroInterpreter)];
tflite::MicroMutableOpResolver<28> resolver;
bool ops_registered;

bool register_ops()
{
    if (ops_registered) return true;
    TfLiteStatus status=kTfLiteOk;
    status=static_cast<TfLiteStatus>(status|resolver.AddConv2D());
    status=static_cast<TfLiteStatus>(status|resolver.AddDepthwiseConv2D());
    status=static_cast<TfLiteStatus>(status|resolver.AddFullyConnected());
    status=static_cast<TfLiteStatus>(status|resolver.AddReshape());
    status=static_cast<TfLiteStatus>(status|resolver.AddLogistic());
    status=static_cast<TfLiteStatus>(status|resolver.AddMean());
    status=static_cast<TfLiteStatus>(status|resolver.AddAveragePool2D());
    status=static_cast<TfLiteStatus>(status|resolver.AddMaxPool2D());
    status=static_cast<TfLiteStatus>(status|resolver.AddAdd());
    status=static_cast<TfLiteStatus>(status|resolver.AddMul());
    status=static_cast<TfLiteStatus>(status|resolver.AddConcatenation());
    status=static_cast<TfLiteStatus>(status|resolver.AddStridedSlice());
    status=static_cast<TfLiteStatus>(status|resolver.AddPad());
    status=static_cast<TfLiteStatus>(status|resolver.AddTranspose());
    status=static_cast<TfLiteStatus>(status|resolver.AddQuantize());
    status=static_cast<TfLiteStatus>(status|resolver.AddDequantize());
    status=static_cast<TfLiteStatus>(status|resolver.AddMinimum());
    status=static_cast<TfLiteStatus>(status|resolver.AddMaximum());
    status=static_cast<TfLiteStatus>(status|resolver.AddRelu());
    status=static_cast<TfLiteStatus>(status|resolver.AddCallOnce());
    status=static_cast<TfLiteStatus>(status|resolver.AddVarHandle());
    status=static_cast<TfLiteStatus>(status|resolver.AddReadVariable());
    status=static_cast<TfLiteStatus>(status|resolver.AddAssignVariable());
    status=static_cast<TfLiteStatus>(status|resolver.AddSplitV());
    ops_registered=status==kTfLiteOk;
    return ops_registered;
}
}

void mochi_wake_unload(void)
{
    ready=false;
    if (interpreter) { interpreter->~MicroInterpreter(); interpreter=nullptr; }
    if (frontend_initialized) FrontendFreeStateContents(&frontend);
    frontend_initialized=false; frontend={}; variables=nullptr;
    free(arena); free(model_bytes); arena=nullptr; model_bytes=nullptr;
}

esp_err_t mochi_wake_load(const char *path,float threshold,unsigned window,size_t bytes)
{
    mochi_wake_unload();
    if (!path || !std::isfinite(threshold) || threshold<=0 || threshold>1 || !window || window>16 || bytes<32768 || bytes>1048576)
        return ESP_ERR_INVALID_ARG;
    FILE *file=fopen(path,"rb");
    if (!file) return ESP_ERR_NOT_FOUND;
    fseek(file,0,SEEK_END); long length=ftell(file); rewind(file);
    if (length<16 || length>2097152) { fclose(file); return ESP_ERR_INVALID_SIZE; }
    model_bytes=static_cast<uint8_t *>(heap_caps_aligned_alloc(16,length,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
    if (!model_bytes) { fclose(file); return ESP_ERR_NO_MEM; }
    bool read=fread(model_bytes,1,length,file)==static_cast<size_t>(length); fclose(file);
    flatbuffers::Verifier verifier(model_bytes,length);
    if (!read || !tflite::VerifyModelBuffer(verifier)) { mochi_wake_unload(); return ESP_ERR_INVALID_RESPONSE; }
    const tflite::Model *model=tflite::GetModel(model_bytes);
    if (model->version()!=TFLITE_SCHEMA_VERSION || !register_ops()) { mochi_wake_unload(); return ESP_ERR_NOT_SUPPORTED; }
    arena=static_cast<uint8_t *>(heap_caps_aligned_calloc(16,1,bytes,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));
    if (!arena) { mochi_wake_unload(); return ESP_ERR_NO_MEM; }
    auto *allocator=tflite::MicroAllocator::Create(arena,bytes);
    if (!allocator || !(variables=tflite::MicroResourceVariables::Create(allocator,32))) { mochi_wake_unload(); return ESP_ERR_NO_MEM; }
    interpreter=new(interpreter_storage) tflite::MicroInterpreter(model,resolver,allocator,variables);
    if (interpreter->AllocateTensors()!=kTfLiteOk || interpreter->inputs_size()!=1 || interpreter->outputs_size()!=1) {
        mochi_wake_unload(); return ESP_ERR_NOT_SUPPORTED;
    }
    auto *input=interpreter->input(0); auto *output=interpreter->output(0);
    if (input->type!=kTfLiteInt8 || input->bytes%40 || input->bytes>400 || input->params.scale<=0 ||
        (output->type!=kTfLiteUInt8 && output->type!=kTfLiteInt8) || output->bytes!=1) {
        mochi_wake_unload(); return ESP_ERR_NOT_SUPPORTED;
    }
    slices=input->bytes/40;
    FrontendConfig config{};
    config.window.size_ms=30; config.window.step_size_ms=10;
    config.filterbank.num_channels=40; config.filterbank.lower_band_limit=125; config.filterbank.upper_band_limit=7500;
    config.noise_reduction.smoothing_bits=10; config.noise_reduction.even_smoothing=.025f;
    config.noise_reduction.odd_smoothing=.06f; config.noise_reduction.min_signal_remaining=.05f;
    config.pcan_gain_control.enable_pcan=1; config.pcan_gain_control.strength=.95f;
    config.pcan_gain_control.offset=80; config.pcan_gain_control.gain_bits=21;
    config.log_scale.enable_log=1; config.log_scale.scale_shift=6;
    if (!FrontendPopulateState(&config,&frontend,16000)) {
        FrontendFreeStateContents(&frontend); frontend={};
        mochi_wake_unload(); return ESP_ERR_NO_MEM;
    }
    frontend_initialized=true; cutoff=threshold; probability_window=window; ready=true;
    mochi_wake_reset();
    return ESP_OK;
}

void mochi_wake_reset(void)
{
    filled=probability_count=probability_pos=warmed_slices=0; probability=0; memset(history,0,sizeof(history));
    if (frontend_initialized) FrontendReset(&frontend);
    if (variables) variables->ResetAll();
    if (interpreter) memset(interpreter->input(0)->data.int8,interpreter->input(0)->params.zero_point,interpreter->input(0)->bytes);
}
bool mochi_wake_ready(void) { return ready.load(); }

bool mochi_wake_feed(const int16_t *pcm,size_t frames)
{
    if (!ready || !pcm) return false;
    bool fired=false;
    while (frames) {
        size_t consumed=0;
        FrontendOutput features=FrontendProcessSamples(&frontend,pcm,frames,&consumed);
        if (!consumed) break;
        pcm+=consumed; frames-=consumed;
        if (features.size!=40) continue;
        warmed_slices++;
        TfLiteTensor *input=interpreter->input(0);
        for (unsigned i=0;i<40;i++) {
            float value=features.values[i]*.0390625f;
            int q=static_cast<int>(std::round(value/input->params.scale))+input->params.zero_point;
            input->data.int8[filled*40+i]=static_cast<int8_t>(std::clamp(q,-128,127));
        }
        if (++filled<slices) continue;
        filled=0;
        int64_t started=esp_timer_get_time();
        if (interpreter->Invoke()!=kTfLiteOk) { failures++; ready=false; break; }
        unsigned elapsed=static_cast<unsigned>(esp_timer_get_time()-started);
        if (elapsed>peak_us) peak_us=elapsed;
        inferences++;
        auto *output=interpreter->output(0);
        int q=output->type==kTfLiteUInt8 ? output->data.uint8[0] : output->data.int8[0];
        float p=(q-output->params.zero_point)*output->params.scale;
        // Quantized resource-variable histories begin at raw zero, not at each
        // tensor's zero point. Flush a complete receptive field before scoring.
        if (warmed_slices<kWarmupSlices) continue;
        history[probability_pos++%probability_window]=p;
        if (probability_count<probability_window) probability_count++;
        float sum=0; for (unsigned i=0;i<probability_count;i++) sum+=history[i];
        probability=sum/probability_count;
        if (probability_count==probability_window && probability>=cutoff) { detections++; fired=true; mochi_wake_reset(); break; }
    }
    return fired;
}

void mochi_wake_diagnose(void)
{
    printf("@mochi_wake ready=%d inference=%u failures=%u detections=%u probability=%.3f peak_us=%u\n",
        ready.load(),inferences.load(),failures.load(),detections.load(),probability.load(),peak_us.load()); fflush(stdout);
}
