"""A persistent GGML T3 with the existing Spanish tokenizer and Torch decoder."""
import ctypes as C
from pathlib import Path
import numpy as np
import torch

I32=np.ctypeslib.ndpointer(dtype=np.int32,ndim=1,flags='C_CONTIGUOUS')
F32=np.ctypeslib.ndpointer(dtype=np.float32,ndim=1,flags='C_CONTIGUOUS')


class HybridT3:
    def __init__(self,library,checkpoint,conditioning,hp,seed=4139,threads=8):
        self.hp=hp;self.seed=seed;self.handle=None
        self.lib=C.CDLL(str(Path(library).resolve()))
        self.lib.mochi_t3_create.argtypes=[C.c_char_p,F32,C.c_int,I32,C.c_int,C.c_int]
        self.lib.mochi_t3_create.restype=C.c_void_p
        self.lib.mochi_t3_generate.argtypes=[C.c_void_p,I32,C.c_int,I32,C.c_int,
            C.c_float,C.c_float,C.c_float,C.c_float,C.c_float,C.c_float,C.c_uint32]
        self.lib.mochi_t3_generate.restype=C.c_int
        self.lib.mochi_t3_destroy.argtypes=[C.c_void_p]
        self.lib.mochi_t3_destroy.restype=None
        self.lib.mochi_t3_logits.argtypes=[C.c_void_p,I32,C.c_int,C.c_int,C.c_int,C.c_float,F32,C.c_int]
        self.lib.mochi_t3_logits.restype=C.c_int
        speaker=np.ascontiguousarray(conditioning.speaker_emb.detach().cpu().numpy().reshape(-1),dtype=np.float32)
        prompt=np.ascontiguousarray(conditioning.cond_prompt_speech_tokens.detach().cpu().numpy().reshape(-1),dtype=np.int32)
        self.handle=self.lib.mochi_t3_create(str(Path(checkpoint).resolve()).encode(),speaker,len(speaker),prompt,len(prompt),threads)
        if not self.handle:raise RuntimeError('Native T3 initialization failed')

    def inference(self,*,t3_cond,text_tokens,temperature=.5,cfg_weight=.5,top_p=1.,min_p=.05,
                  repetition_penalty=1.2,max_new_tokens=1000,**kwargs):
        if not self.handle:raise RuntimeError('Native T3 is closed')
        ids=np.ascontiguousarray(text_tokens[0].detach().cpu().numpy().reshape(-1),dtype=np.int32)
        if not 2<=len(ids)<=256:raise ValueError('Text exceeds native T3 input bounds')
        output=np.empty(self.hp.speech_tokens_dict_size*2,dtype=np.float32)
        exaggeration=float(t3_cond.emotion_adv.reshape(-1)[0])
        from transformers.generation.logits_process import (
            RepetitionPenaltyLogitsProcessor,MinPLogitsWarper,TopPLogitsWarper)
        repetition=RepetitionPenaltyLogitsProcessor(float(repetition_penalty))
        minimum=MinPLogitsWarper(min_p)
        nucleus=TopPLogitsWarper(top_p)
        history=torch.tensor([[self.hp.start_speech_token]],dtype=torch.long)
        predicted=[];previous=0
        for step in range(min(max_new_tokens,500)):
            count=self.lib.mochi_t3_logits(self.handle,ids,len(ids),previous,step,exaggeration,output,len(output))
            if count!=len(output):raise RuntimeError('Native T3 inference failed: '+str(count))
            pair=torch.from_numpy(output.copy().reshape(2,-1))
            logits=pair[0:1]+cfg_weight*(pair[0:1]-pair[1:2])
            logits=repetition(history,logits)
            if temperature!=1.:logits=logits/temperature
            logits=nucleus(history,minimum(history,logits))
            token=torch.multinomial(torch.softmax(logits,dim=-1),num_samples=1)
            predicted.append(token);history=torch.cat([history,token],dim=1)
            previous=int(token.item())
            if previous==self.hp.stop_speech_token:return torch.cat(predicted,dim=1)
        raise RuntimeError('Native T3 did not reach the end of speech')

    def close(self):
        if self.handle:self.lib.mochi_t3_destroy(self.handle);self.handle=None
