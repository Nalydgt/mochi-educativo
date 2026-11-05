"""Prepare a quantized microWakeWord candidate using local Spanish synthesis.

Synthetic evaluation is explicitly separate from the required on-device trial.
No household recordings are captured by this process.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import wave

os.environ.setdefault('CUDA_VISIBLE_DEVICES','-1')
os.environ.setdefault('TF_NUM_INTRAOP_THREADS','2')
os.environ.setdefault('TF_NUM_INTEROP_THREADS','1')
os.environ.setdefault('OMP_NUM_THREADS','2')

import numpy as np
from placement import positive_context
framework=Path(__file__).resolve().parents[1]/'micro-wake-word'
if framework.is_dir(): sys.path.insert(0,str(framework))


def progress(directory,stage,percent):
    temporary=directory/'progress.tmp'
    temporary.write_text(json.dumps({'stage':stage,'progress':percent}))
    temporary.replace(directory/'progress.json')


def features(audio):
    from pymicro_features import MicroFrontend
    frontend=MicroFrontend(); result=[]
    pcm=np.asarray(audio,dtype='<i2').tobytes()
    for position in range(0,len(pcm)-319,320):
        frame=frontend.process_samples(pcm[position:position+320])
        if frame.features: result.append(frame.features)
    return np.asarray(result,dtype=np.float32)


def synthesized(voice,text,speaker,speed):
    from piper import SynthesisConfig
    buffer=io.BytesIO()
    with wave.open(buffer,'wb') as output:
        voice.synthesize_wav(text,output,syn_config=SynthesisConfig(speaker_id=speaker,length_scale=speed))
    with wave.open(io.BytesIO(buffer.getvalue()),'rb') as source:
        rate=source.getframerate(); channels=source.getnchannels()
        data=np.frombuffer(source.readframes(source.getnframes()),dtype='<i2').reshape(-1,channels).mean(axis=1)
    if rate!=16000:
        from scipy.signal import resample_poly
        data=resample_poly(data,16000,rate)
    # Preserve an entire keyword, then add context in the streaming evaluation.
    return np.clip(data,-32768,32767).astype(np.int16)


def augmented(audio,rng):
    ratio=rng.uniform(.82,1.18)
    n=max(1,int(len(audio)/ratio))
    altered=np.interp(np.arange(n)*ratio,np.arange(len(audio)),audio)
    altered*=rng.uniform(.25,1.0)
    rms=max(1,float(np.sqrt(np.mean(altered**2))))
    altered+=rng.normal(0,rms/(10**(rng.uniform(8,30)/20)),n)
    return np.pad(np.clip(altered,-32768,32767).astype(np.int16),(rng.integers(800,6400),rng.integers(800,4800)))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--directory',type=Path,required=True)
    parser.add_argument('--name',required=True)
    parser.add_argument('--voices',type=Path,required=True)
    args=parser.parse_args(); directory=args.directory; directory.mkdir(parents=True,exist_ok=True)
    progress(directory,'preparing',1)
    import tensorflow as tf
    from piper import PiperVoice
    from piper.config import PiperConfig
    import onnxruntime as ort
    import yaml
    from microwakeword import mixednet,utils
    from microwakeword.layers.modes import Modes

    seed=int(hashlib.sha256(args.name.casefold().encode()).hexdigest()[:8],16)
    rng=np.random.default_rng(seed); tf.keras.utils.set_random_seed(seed)
    voice_path=args.voices/'es_ES-sharvard-medium.onnx'
    def load_voice(path):
        # ORT's per-session default uses one thread per physical core. Multiple
        # loaded voices must share this container's two-CPU budget instead.
        session_options=ort.SessionOptions()
        session_options.intra_op_num_threads=2
        session_options.inter_op_num_threads=1
        session_options.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
        session_options.add_session_config_entry('session.intra_op.allow_spinning','0')
        with Path(str(path)+'.json').open(encoding='utf-8') as config_file:
            configuration=PiperConfig.from_dict(json.load(config_file))
        return PiperVoice(config=configuration,session=ort.InferenceSession(str(path),
            sess_options=session_options,providers=['CPUExecutionProvider']))
    voice=load_voice(voice_path)
    profile_keys={id(voice):hashlib.sha256(voice_path.read_bytes()).hexdigest()}
    profiles=[(voice,0),(voice,1)]
    from urllib.request import urlopen
    import shutil
    def training_voice(locale,speaker,quality):
        filename=f'{locale}-{speaker}-{quality}.onnx'
        target=args.voices/'wake-training'/filename
        language=locale.split('_')[0]
        base=f'https://huggingface.co/rhasspy/piper-voices/resolve/main/{language}/{locale}/{speaker}/{quality}/{filename}'
        target.parent.mkdir(parents=True,exist_ok=True)
        for suffix in ('','.json'):
            destination=Path(str(target)+suffix)
            if destination.is_file(): continue
            temporary=Path(str(destination)+'.partial')
            import time
            for attempt in range(3):
                try:
                    with urlopen(base+suffix,timeout=90) as source,temporary.open('wb') as output:
                        expected=source.headers.get('Content-Length')
                        shutil.copyfileobj(source,output)
                    if expected and temporary.stat().st_size!=int(expected):
                        raise OSError('Incomplete training voice download')
                    break
                except (OSError,TimeoutError):
                    if attempt==2: raise
                    time.sleep(.5*(attempt+1))
            temporary.replace(destination)
        loaded=load_voice(target)
        profile_keys[id(loaded)]=hashlib.sha256(target.read_bytes()).hexdigest()
        return loaded
    for locale,speaker,quality in [('es_ES','carlfm','x_low'),('es_ES','mls_10246','low'),
                                  ('es_MX','ald','medium'),('es_MX','claude','high')]:
        profiles.append((training_voice(locale,speaker,quality),0))
        progress(directory,'preparing',min(10,len(profiles)))
    # Additional identities supplement native Spanish voices. An earlier corpus
    # was dominated by English-trained identities despite Spanish phonemes:
    # isolated-word training recall was 100%, held-out Spanish recall near zero.
    multi=training_voice('en_US','libritts_r','medium')
    multi.config.espeak_voice='es'
    speakers=np.linspace(0,multi.config.num_speakers-1,16,dtype=int)
    profiles.extend((multi,int(speaker)) for speaker in speakers)
    validation_profile=profiles.pop(2)  # carlfm is never a training speaker
    # Previously exposed evaluation identities can now be training data, but
    # cannot serve as the independent final test for this pipeline revision.
    profiles.append((training_voice('es_ES','davefx','medium'),0))
    profiles.append((training_voice('es_ES','mls_9972','low'),0))
    held_voice=training_voice('es_AR','daniela','high')
    example_cache=args.voices/'wake-examples'; example_cache.mkdir(parents=True,exist_ok=True)
    def cached_synth(v,text,speaker,speed):
        key=hashlib.sha256(json.dumps([profile_keys[id(v)],v.config.espeak_voice,
            text,speaker,speed],ensure_ascii=False).encode()).hexdigest()
        destination=example_cache/(key+'.wav')
        if destination.is_file():
            with wave.open(str(destination),'rb') as source:
                if source.getframerate()!=16000 or source.getnchannels()!=1 or source.getsampwidth()!=2:
                    raise ValueError('Invalid synthetic example cache')
                return np.frombuffer(source.readframes(source.getnframes()),dtype='<i2')
        audio=synthesized(v,text,speaker,speed)
        temporary=destination.with_suffix('.partial')
        with wave.open(str(temporary),'wb') as output:
            output.setnchannels(1); output.setsampwidth(2); output.setframerate(16000)
            output.writeframes(audio.tobytes())
        temporary.replace(destination)
        return audio
    negatives=[
        'Hola, buenos dias.','Que tal estas hoy.','Vamos a pasear.','Tengo una mochila roja.',
        'Esta noche iremos en coche.','Hace mucho calor.','Voy a preparar la comida.',
        'Me gusta la musica.','Donde has dejado las llaves.','La ventana esta abierta.',
        'Estamos viendo la television.','Quiero jugar contigo.','Hoy tengo un poco de sueno.',
        'El perro esta en el parque.','Vuelve dentro de un rato.','Muchas gracias por venir.',
        'Las noticias del dia.','Voy a llamar por telefono.','Uno dos tres cuatro cinco.',
        'Canta una cancion.','Vamos a dormir.','Es un momento muy especial.',
        'La lluvia cae en el jardin.','Tenemos que comprar pan.','No escucho nada.',
        'La luna esta muy bonita.','Ponlo en la mesa.','Me puedes ayudar un momento.',
        'El reloj marca las ocho.','Ya he terminado de trabajar.',
    ]
    negatives+=['Hola','Gracias','Agua','Comida','Coche','Noche','Mucho','Mochila',
        'Mocha','Mochito','Ocho','Mami','Mira','Mola','Luna','Mosca','Moki']
    # Every post-name training phrase must also occur without the keyword.
    # Otherwise the network can learn the question instead of the name itself.
    following_phrases=('hola que tal estas','vamos a jugar juntos','quiero contarte algo',
                       'estas ahi','me escuchas','buenos dias')
    negatives+=list(following_phrases)
    named_word=re.compile(r'(?<!\w)'+re.escape(args.name)+r'(?!\w)',re.IGNORECASE)
    negatives=[s for s in negatives if not named_word.search(s)]
    variants=[args.name[1:],args.name[:-1],args.name+'la',args.name+'ito']
    negatives+=['Digo '+s for s in variants if len(s)>1 and s.casefold()!=args.name.casefold()]
    model_parser=argparse.ArgumentParser(); mixednet.model_parameters(model_parser)
    flags=model_parser.parse_args(['--pointwise_filters','96,96,96','--repeat_in_block','1,1,1',
        '--mixconv_kernel_sizes','[5],[9],[13]','--residual_connection','0,0,0',
        '--first_conv_filters','32','--first_conv_kernel_size','5','--stride','3','--pooled','1'])
    config_file=directory/'training.yaml'
    config_file.write_text(yaml.safe_dump({'window_step_ms':10,'clip_duration_ms':1500,'train_dir':str(directory/'trained')}))
    # Use the upstream shape calculation without importing the optional dataset stack.
    final_slices=1+(16000*1500//1000-480)//480
    total_slices=final_slices+mixednet.spectrogram_slices_dropped(flags)
    config={'train_dir':str(directory/'trained'),'stride':3,'window_step_ms':10,
            'spectrogram_length':total_slices,'spectrogram_length_final_layer':final_slices,
            'training_input_shape':(total_slices,40),'flags':vars(flags)}
    count=config['training_input_shape'][0]
    window_samples=(count+2)*160
    warmup_slices=150
    def fit_feature(audio):
        f=features(audio)
        if len(f)<count: f=np.pad(f,((count-len(f),0),(0,0)))
        # A slice would retain the entire, often much longer context array for
        # every example until the dataset was assembled, exhausting trainer RAM.
        return f[-count:].copy()
    dataset=directory/'training.npz'
    placement_stats={'generated':0,'oversized':0}
    dataset_ready=False
    if dataset.is_file():
        with np.load(dataset) as stored:
            dataset_ready=int(stored.get('version',0))==10
            if dataset_ready:x,y,vx,vy=(stored[key] for key in ('x','y','vx','vy'))
    if not dataset_ready:
        def recordings(v,speaker):
            positive=[]; negative=[]
            for speed in (.75,.9,1.05,1.2):
                word=cached_synth(v,args.name,speaker,speed)
                # Give the isolated keyword half the positive examples. In v8
                # it was only one seventh, and the validation model rejected it.
                positive.extend([(word,'keyword')]*len(following_phrases))
                # Include coarticulation and speech immediately after the name.
                # Keep only the beginning; the full sentence can outlast the
                # model's receptive field and otherwise lose the keyword.
                for following in following_phrases:
                    continuous=cached_synth(v,args.name+' '+following,speaker,speed)
                    end=min(len(continuous),round(len(word)*1.15)+1920)
                    positive.append((continuous[:end],'continuous'))
            for index,text in enumerate(negatives):
                negative.append(cached_synth(v,text,speaker,.85+(index%3)*.15))
            return positive,negative
        raw_positive=[]; raw_negative=[]
        for profile_index,(v,speaker) in enumerate(profiles):
            progress(directory,'preparing',10+int(profile_index/len(profiles)*9))
            positive,negative=recordings(v,speaker)
            # Balance both labels by source. Native Spanish accounts for most
            # examples; repeated augmentation never counts as extra speakers.
            weight=1 if v is multi else 8
            raw_positive.extend(positive*weight); raw_negative.extend(negative*weight)
        def build_examples(positive,negative,repeats):
            xx=[]; yy=[]; kinds=[]
            def context():
                mode=rng.random()
                if mode<1/3:
                    return np.zeros(int(rng.integers(24000,48000)),dtype=np.int16)
                if mode<2/3:
                    return augmented(negative[int(rng.integers(len(negative)))],rng)
                return rng.normal(0,rng.uniform(0,100),int(rng.integers(16000,48000))).astype(np.int16)
            for audio,kind in positive:
                for _ in range(repeats):
                    before=context()
                    joined=positive_context(audio,before,rng,window_samples)
                    if joined is None:
                        placement_stats['oversized']+=1
                        continue
                    placement_stats['generated']+=1
                    if len(joined)<window_samples:joined=np.pad(joined,(window_samples-len(joined),0))
                    xx.append(fit_feature(joined)); yy.append(1); kinds.append(kind)
            for audio in negative:
                for _ in range(max(6,repeats//2)):
                    altered=augmented(audio,rng)
                    # A streaming detector must reject word onsets as well as
                    # complete sentences. Use the same frontend history as the
                    # positive class; otherwise history alone predicts the label.
                    if rng.random()<.5 and len(altered)>160:
                        altered=altered[:int(rng.integers(160,len(altered)+1))]
                    xx.append(fit_feature(np.concatenate([context(),altered]))); yy.append(0); kinds.append('negative')
            for _ in range(300):
                xx.append(fit_feature(rng.normal(0,rng.uniform(0,900),window_samples).astype(np.int16))); yy.append(0); kinds.append('noise')
            for _ in range(60):
                xx.append(fit_feature(np.zeros(window_samples,dtype=np.int16))); yy.append(0); kinds.append('silence')
            return np.asarray(xx,np.float32),np.asarray(yy,np.float32),np.asarray(kinds)
        # More independent speaker identities, fewer copies of each recording.
        # Repeated augmentation cannot replace acoustic speaker diversity.
        x,y,training_kind=build_examples(raw_positive,raw_negative,8)
        vx,vy,validation_kind=build_examples(*recordings(*validation_profile),12)
        if not np.any(y):raise ValueError('Activation word exceeds detector window')
        np.savez_compressed(dataset,x=x,y=y,vx=vx,vy=vy,version=10,
                            training_kind=training_kind,validation_kind=validation_kind)
    permutation=rng.permutation(len(y)); x,y=x[permutation],y[permutation]
    calibration=x[:96].copy()
    def spectral_augmentation(batch,labels):
        # Training-only masks, following microWakeWord's SpecAugment policy.
        # The exported detector receives the unmodified microphone features.
        batch_size=tf.shape(batch)[0]
        for axis,maximum in ((1,5),(1,5),(2,5),(2,5)):
            limit=tf.shape(batch)[axis]
            width=tf.random.uniform([batch_size,1,1],0,maximum+1,dtype=tf.int32)
            start=tf.random.uniform([batch_size,1,1],0,limit-maximum,dtype=tf.int32)
            positions=tf.reshape(tf.range(limit),[1,-1,1] if axis==1 else [1,1,-1])
            batch=tf.where((positions>=start)&(positions<start+width),0.,batch)
        return batch,labels
    training=tf.data.Dataset.from_tensor_slices((x,y)).shuffle(min(len(y),4096),seed=seed).batch(64)
    training=training.map(spectral_augmentation,num_parallel_calls=1).prefetch(1)
    options=tf.data.Options(); options.threading.private_threadpool_size=2
    training=training.with_options(options)
    del x,y
    model=mixednet.model(flags,config['training_input_shape'],None)
    model.compile(optimizer=tf.keras.optimizers.Adam(.001),loss='binary_crossentropy',metrics=['accuracy'])
    checkpoint=directory/'best.weights.h5'
    if checkpoint.is_file(): model.load_weights(checkpoint)
    class Report(tf.keras.callbacks.Callback):
        def on_epoch_end(self,epoch,logs=None):
            progress(directory,'training',20+int((epoch+1)/35*55))
    progress(directory,'training',20)
    model.fit(training,epochs=35,validation_data=(vx,vy),class_weight={0:1.,1:1.},
              callbacks=[Report(),tf.keras.callbacks.ModelCheckpoint(str(checkpoint),save_weights_only=True,
                  save_best_only=True,monitor='val_loss'),
                  tf.keras.callbacks.EarlyStopping(monitor='val_loss',patience=7,restore_best_weights=True)],verbose=2)
    model.load_weights(checkpoint)
    with np.load(dataset) as stored:validation_kind=stored['validation_kind']
    window_scores=model.predict(vx,batch_size=64,verbose=0).reshape(-1)
    window_validation={str(kind):{'count':int(np.sum(validation_kind==kind)),
        'mean_score':float(window_scores[validation_kind==kind].mean()),
        'accept_rate_at_05':float((window_scores[validation_kind==kind]>=.5).mean())}
        for kind in np.unique(validation_kind)}
    progress(directory,'checking',77)
    utils.convert_model_saved(model,config,'stream',Modes.STREAM_INTERNAL_STATE_INFERENCE)
    converter=tf.lite.TFLiteConverter.from_saved_model(str(directory/'trained/stream'))
    converter.optimizations=[tf.lite.Optimize.DEFAULT]
    converter._experimental_variable_quantization=True
    converter.target_spec.supported_ops=[tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    converter.inference_input_type=tf.int8; converter.inference_output_type=tf.uint8
    def representative():
        for f in calibration:
            for pos in range(0,len(f)-3,3): yield [f[None,pos:pos+3,:].astype(np.float32)]
    converter.representative_dataset=representative
    (directory/'model.tflite').write_bytes(converter.convert())
    interpreter=tf.lite.Interpreter(model_path=str(directory/'model.tflite'),num_threads=2)
    interpreter.allocate_tensors(); inp=interpreter.get_input_details()[0]; out=interpreter.get_output_details()[0]
    def score(audio):
        # Resource-variable streaming state is not reliably cleared by the Python
        # reset_all_variables API. Use a fresh interpreter for each held-out clip.
        trial=tf.lite.Interpreter(model_path=str(directory/'model.tflite'),num_threads=2)
        trial.allocate_tensors(); f=features(np.pad(audio,(warmup_slices*160,0))); predictions=[]
        scale,zero=inp['quantization']; out_scale,out_zero=out['quantization']
        for pos in range(0,len(f)-3,3):
            data=np.clip(np.round(f[pos:pos+3]/scale)+zero,-128,127).astype(np.int8)[None,...]
            trial.set_tensor(inp['index'],data); trial.invoke()
            if pos+3>=warmup_slices:
                predictions.append((float(trial.get_tensor(out['index']).flat[0])-out_zero)*out_scale)
        return float(np.convolve(predictions,np.ones(5)/5,mode='valid').max()) if len(predictions)>=5 else 0.
    def evaluate(v,speaker,sentences):
        positives=[]; negatives_result=[]
        for speed in (.75,.9,1.05,1.2):
            for sentence in sentences:
                audio=cached_synth(v,sentence,speaker,speed)
                for _ in range(3):positives.append(score(augmented(audio,rng)))
        for text in negatives:
            negatives_result.append(score(augmented(cached_synth(v,text,speaker,1.0),rng)))
        return positives,negatives_result
    validation_positive,validation_negative=evaluate(*validation_profile,
        (args.name,args.name+', hola que tal estas',args.name+', vamos a jugar juntos'))
    thresholds=[.5,.6,.7,.8,.85,.9,.95,.98]
    chosen=next((threshold for threshold in thresholds
        if np.mean(np.array(validation_positive)>=threshold)>=.95
        and not any(s>=threshold for s in validation_negative)),None)
    positive_scores=[]; negative_scores=[]
    # The final speaker and following phrases are held out. Select the threshold
    # on validation only; the independent test cannot tune its own acceptance.
    for speed in (.75,.9,1.05,1.2):
        for sentence in (args.name,args.name+', sabes que hora es?',args.name+', quiero ir al parque'):
            audio=cached_synth(held_voice,sentence,0,speed)
            for _ in range(3): positive_scores.append(score(augmented(audio,rng)))
    for text in negatives:
        audio=cached_synth(held_voice,text,0,1.0)
        negative_scores.append(score(augmented(audio,rng)))
    passed=chosen is not None and np.mean(np.array(positive_scores)>=chosen)>=.95 and not any(s>=chosen for s in negative_scores)
    report={'passed':passed,'pipeline':'mww-mochi-v10','evaluation':'independent-held-out-synthetic-speaker',
        'physical_test_required':True,'probability_cutoff':chosen or .95,'sliding_window':5,'arena_bytes':524288,
        'warmup_slices':warmup_slices,
        'positive_clips':len(positive_scores),'negative_clips':len(negative_scores),
        'recall':float(np.mean(np.array(positive_scores)>=(chosen or .95))),
        'negative_false_accepts':sum(s>=(chosen or .95) for s in negative_scores),
        'positive_scores':positive_scores,'negative_scores':negative_scores,
        'threshold_selected_on':'validation_only','validation_positive':validation_positive,
        'window_validation':window_validation,
        'validation_negative':validation_negative,'placement':placement_stats,'held_out_voice':'es_AR-daniela-high',
        'training_speakers':len(profiles),'native_training_speakers':sum(v is not multi for v,_ in profiles),
        'native_source_weight':8,'supplemental_source_weight':1,
        'validation_speakers':1,'held_out_speakers':1,'name':args.name}
    (directory/'report.json').write_text(json.dumps(report,indent=2))
    progress(directory,'checking',99)
    if not report['passed']: raise SystemExit(2)


if __name__=='__main__': main()
