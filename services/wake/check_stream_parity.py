"""Compare held-out feature windows before/after streaming quantization, read-only."""
import argparse,json,os
from pathlib import Path
import sys

os.environ.setdefault('CUDA_VISIBLE_DEVICES','-1')
os.environ.setdefault('TF_NUM_INTRAOP_THREADS','2')
os.environ.setdefault('TF_NUM_INTEROP_THREADS','1')
import numpy as np
import tensorflow as tf

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('directory',type=Path)
args=parser.parse_args();directory=args.directory
framework=Path(__file__).resolve().parents[1]/'micro-wake-word'
if framework.is_dir():sys.path.insert(0,str(framework))
from microwakeword import mixednet
flags_parser=argparse.ArgumentParser();mixednet.model_parameters(flags_parser)
flags=flags_parser.parse_args(['--pointwise_filters','96,96,96','--repeat_in_block','1,1,1',
    '--mixconv_kernel_sizes','[5],[9],[13]','--residual_connection','0,0,0',
    '--first_conv_filters','32','--first_conv_kernel_size','5','--stride','3','--pooled','1'])
with np.load(directory/'training.npz') as stored:
    all_labels=stored['vy'];all_windows=stored['vx']
    indices=np.r_[np.flatnonzero(all_labels>0)[:6],np.flatnonzero(all_labels==0)[:6]]
    windows=all_windows[indices];labels=all_labels[indices]
model=mixednet.model(flags,windows.shape[1:],None)
model.load_weights(directory/'best.weights.h5')
all_scores=model.predict(all_windows,batch_size=64,verbose=0).reshape(-1)
positives=all_scores[all_labels>0]
print(json.dumps({'validation_examples':len(all_labels),'positive_examples':len(positives),
    'positive_recall_at_05':float((positives>=.5).mean()),
    'negative_false_accept_rate_at_05':float((all_scores[all_labels==0]>=.5).mean()),
    'positive_score_percentiles':np.percentile(positives,[0,25,50,75,100]).tolist()}),flush=True)
if len(positives)==4*7*12:
    grouped=positives.reshape(4,7,12)
    print(json.dumps({'validation_keyword_alone_score':float(grouped[:,0,:].mean()),
        'validation_following_speech_scores':grouped[:,1:,:].mean(axis=(0,2)).tolist(),
        'keyword_alone_recall_at_05':float((grouped[:,0,:]>=.5).mean()),
        'following_speech_recall_at_05':float((grouped[:,1:,:]>=.5).mean())}),flush=True)
offline=np.asarray(model(windows,training=False)).reshape(-1)
reports=[]
for index,(window,label,expected) in enumerate(zip(windows,labels,offline)):
    trial=tf.lite.Interpreter(model_path=str(directory/'model.tflite'),num_threads=2)
    trial.allocate_tensors();inp=trial.get_input_details()[0];out=trial.get_output_details()[0]
    scale,zero=inp['quantization'];out_scale,out_zero=out['quantization']
    feature_stream=np.concatenate([np.zeros((150,40),np.float32),window])
    for position in range(0,len(feature_stream)-2,3):
        data=np.clip(np.rint(feature_stream[position:position+3]/scale)+zero,-128,127).astype(np.int8)[None,...]
        trial.set_tensor(inp['index'],data);trial.invoke()
    actual=(float(trial.get_tensor(out['index']).flat[0])-out_zero)*out_scale
    item={'index':index,'label':int(label),'keras_score':float(expected),'stream_score':actual,
        'absolute_difference':float(abs(expected-actual))}
    reports.append(item)
print(json.dumps({'read_only':True,'feature_window_shape':list(windows.shape[1:]),
    'mean_absolute_difference':float(np.mean([r['absolute_difference'] for r in reports])),
    'samples':reports}),flush=True)
