"""Compare fixed-token native prefill and decode logits with the original model."""
import ctypes as C
import numpy as np
import torch
import torch.nn.functional as F
from hybrid_t3 import I32,F32


def check(model,adapter):
    t3=model.t3
    ids=model.tokenizer.text_to_tokens('Me encuentro genial.',language_id='es')
    ids=F.pad(F.pad(torch.cat([ids,ids],dim=0),(1,0),value=t3.hp.start_text_token),
              (0,1),value=t3.hp.stop_text_token)
    native_ids=np.ascontiguousarray(ids[0].numpy().reshape(-1),dtype=np.int32)
    adapter.lib.mochi_t3_logits.argtypes=[C.c_void_p,I32,C.c_int,C.c_int,C.c_int,C.c_float,F32,C.c_int]
    adapter.lib.mochi_t3_logits.restype=C.c_int
    logits=np.empty(t3.hp.speech_tokens_dict_size*2,dtype=np.float32)
    rows=[]
    with torch.inference_mode():
        bos=torch.full((1,1),t3.hp.start_speech_token,dtype=torch.long)
        initial=torch.full_like(ids[:,:1],t3.hp.start_speech_token)
        embeds,_=t3.prepare_input_embeds(t3_cond=model.conds.t3,text_tokens=ids,speech_tokens=initial,cfg_weight=.5)
        embedding=t3.speech_emb(bos)+t3.speech_pos_emb.get_fixed_embedding(0)
        inputs=torch.cat([embeds,torch.cat([embedding,embedding],dim=0)],dim=1)
        past=None;previous=0
        for step in range(3):
            result=t3.tfmr(inputs_embeds=inputs,past_key_values=past,use_cache=True)
            past=result.past_key_values
            reference=t3.speech_head(result.last_hidden_state[:,-1,:]).float().numpy()
            n=adapter.lib.mochi_t3_logits(adapter.handle,native_ids,len(native_ids),previous,step,.25,logits,len(logits))
            if n!=len(logits):raise RuntimeError('Native parity call failed: '+str(n))
            candidate=logits.reshape(reference.shape)
            cosine=float(np.sum(reference*candidate)/(np.linalg.norm(reference)*np.linalg.norm(candidate)))
            relative_rmse=float(np.linalg.norm(reference-candidate)/np.linalg.norm(reference))
            rows.append({'speech_step':step,'cosine':cosine,'relative_rmse':relative_rmse})
            combined=reference[0]+.5*(reference[0]-reference[1]);previous=int(np.argmax(combined))
            token=torch.tensor([[previous]],dtype=torch.long)
            embedding=t3.speech_emb(token)+t3.speech_pos_emb.get_fixed_embedding(step+1)
            inputs=torch.cat([embedding,embedding],dim=0)
    return {'passed':all(row['cosine']>=.99 and row['relative_rmse']<.15 for row in rows),'steps':rows}
