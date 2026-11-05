// Mochi CPU adapter for the MIT-licensed chatterbox.cpp multilingual T3.
// The Python tokenizer, approved conditioning, S3Gen and watermark stay in use.
#include "chatterbox_t3_internal.h"
#include "t3_mtl.h"
#include <algorithm>
#include <cstdint>
#include <random>
#include <vector>
using namespace tts_cpp::chatterbox::detail;
namespace tts_cpp::chatterbox::detail { void mochi_set_speech_position(int position); }

struct MochiT3 {
    chatterbox_model model{};
    ggml_gallocr_t allocator=nullptr;
    int threads=8;
    int diagnostic_position=0;
    ~MochiT3() {
        if (allocator) ggml_gallocr_free(allocator);
        if (model.buffer_stack || model.ctx_stack) t3_stack_unregister(model.buffer_stack,model.ctx_stack);
        for (auto buffer:{model.buffer_w,model.buffer_kv,model.buffer_stack,model.buffer_override})
            if (buffer) ggml_backend_buffer_free(buffer);
        if (model.backend) ggml_backend_free(model.backend);
        for (auto context:{model.ctx_w,model.ctx_kv,model.ctx_stack,model.ctx_override})
            if (context) ggml_free(context);
    }
};

extern "C" void *mochi_t3_create(const char *path,const float *speaker,int speaker_size,
                                 const int32_t *prompt,int prompt_size,int threads) {
    if (!path || !speaker || !prompt || speaker_size!=256 || prompt_size<1 || prompt_size>250 || threads<1 || threads>16) return nullptr;
    auto *state=new MochiT3();
    try {
        state->threads=threads;
        if (!load_model_gguf(path,state->model,768,0) || state->model.hparams.variant!=CHBX_VARIANT_MTL) throw 1;
        auto &m=state->model;
        if (!m.builtin_speaker_emb || ggml_nelements(m.builtin_speaker_emb)!=speaker_size) throw 2;
        ggml_backend_tensor_set(m.builtin_speaker_emb,speaker,0,speaker_size*sizeof(float));
        if (ggml_nelements(m.builtin_cond_prompt_tokens)!=prompt_size) {
            ggml_init_params parameters{ggml_tensor_overhead()*2,nullptr,true};
            m.ctx_override=ggml_init(parameters);
            if (!m.ctx_override) throw 3;
            auto *tensor=ggml_new_tensor_1d(m.ctx_override,GGML_TYPE_I32,prompt_size);
            m.buffer_override=ggml_backend_alloc_ctx_tensors(m.ctx_override,m.backend);
            if (!m.buffer_override) throw 4;
            m.builtin_cond_prompt_tokens=tensor;m.hparams.cond_prompt_len=prompt_size;
        }
        ggml_backend_tensor_set(m.builtin_cond_prompt_tokens,prompt,0,prompt_size*sizeof(int32_t));
        state->allocator=ggml_gallocr_new(ggml_backend_get_default_buffer_type(m.backend));
        if (!state->allocator) throw 5;
        return state;
    } catch (...) {delete state;return nullptr;}
}

extern "C" int mochi_t3_generate(void *handle,const int32_t *input,int count,int32_t *output,int capacity,
    float temperature,float cfg,float exaggeration,float top_p,float min_p,float repetition,uint32_t seed) {
    if (!handle || !input || !output || count<2 || count>256 || capacity<1 || capacity>500) return -1;
    auto &state=*static_cast<MochiT3 *>(handle);
    try {
        std::vector<int32_t> tokens(input,input+count),generated;
        // HF gather/scatter penalizes each distinct ID once, including BOS.
        // Passing repeated IDs to the upstream loop would compound penalties.
        std::vector<int32_t> history{state.model.hparams.start_speech_token};
        for (auto token:tokens) if (token<0 || token>=state.model.hparams.n_text_vocab) return -2;
        std::vector<float> conditional,unconditional;
        int position=0;
        if (!eval_prompt_mtl(state.model,state.allocator,state.threads,tokens,exaggeration,
                            conditional,unconditional,position)) return -3;
        chatterbox_sampling_params sampling;
        sampling.top_k=0;sampling.top_p=top_p;sampling.min_p=min_p;
        sampling.temp=temperature;sampling.cfg_weight=cfg;sampling.repeat_penalty=repetition;
        std::mt19937 rng(seed);
        while (static_cast<int>(generated.size())<capacity) {
            int32_t next=sample_next_token_mtl(conditional,unconditional,history,sampling,rng,state.model.hparams.stop_speech_token);
            if (next==state.model.hparams.stop_speech_token) break;
            generated.push_back(next);
            if (std::find(history.begin(),history.end(),next)==history.end()) history.push_back(next);
            if (position+1>=state.model.hparams.n_ctx) return -4;
            // Learned speech positions start at 1; RoPE/KV positions include
            // the conditioning and text prefix. They are different indices.
            mochi_set_speech_position(static_cast<int>(generated.size()));
            if (!eval_step_mtl(state.model,state.allocator,state.threads,position++,next,conditional,unconditional)) return -5;
        }
        if (generated.empty() || static_cast<int>(generated.size())==capacity) return -6;
        std::copy(generated.begin(),generated.end(),output);
        return static_cast<int>(generated.size());
    } catch (...) {return -7;}
}

extern "C" void mochi_t3_destroy(void *handle) {delete static_cast<MochiT3 *>(handle);}

// Numerical parity checks use exactly the same prefill/step kernels, with
// caller-chosen previous speech tokens instead of sampling different RNGs.
extern "C" int mochi_t3_logits(void *handle,const int32_t *ids,int count,int previous_token,
                                int speech_position,float exaggeration,float *output,int capacity) {
    if (!handle || !output) return -1;
    auto &state=*static_cast<MochiT3 *>(handle);
    if (capacity<2*state.model.hparams.n_speech_vocab) return -2;
    try {
        std::vector<float> conditional,unconditional;
        if (speech_position==0) {
            if (!ids || count<2 || count>256) return -3;
            std::vector<int32_t> tokens(ids,ids+count);
            if (!eval_prompt_mtl(state.model,state.allocator,state.threads,tokens,exaggeration,
                    conditional,unconditional,state.diagnostic_position)) return -4;
        } else {
            mochi_set_speech_position(speech_position);
            if (!eval_step_mtl(state.model,state.allocator,state.threads,state.diagnostic_position++,
                    previous_token,conditional,unconditional)) return -5;
        }
        std::copy(conditional.begin(),conditional.end(),output);
        std::copy(unconditional.begin(),unconditional.end(),output+conditional.size());
        return static_cast<int>(conditional.size()+unconditional.size());
    } catch (...) {return -6;}
}
