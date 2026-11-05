"""Read-only diagnosis: distinguish fitting from held-out speaker generalization.

Print numeric synthetic-data scores only. This never trains, selects a
threshold, modifies a job, or makes a candidate eligible for installation.
"""
import argparse,json,os,sys
from pathlib import Path

os.environ.setdefault('CUDA_VISIBLE_DEVICES','-1')
os.environ.setdefault('TF_NUM_INTRAOP_THREADS','2')
os.environ.setdefault('TF_NUM_INTEROP_THREADS','1')
import numpy as np

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    args=parser.parse_args()
    framework=Path(__file__).resolve().parents[1]/'micro-wake-word'
    if framework.is_dir():sys.path.insert(0,str(framework))
    from microwakeword import mixednet
    flags_parser=argparse.ArgumentParser();mixednet.model_parameters(flags_parser)
    flags=flags_parser.parse_args(['--pointwise_filters','96,96,96','--repeat_in_block','1,1,1',
        '--mixconv_kernel_sizes','[5],[9],[13]','--residual_connection','0,0,0',
        '--first_conv_filters','32','--first_conv_kernel_size','5','--stride','3','--pooled','1'])
    rng=np.random.default_rng(4139);samples=[];groups=[]
    with np.load(args.directory/'training.npz') as stored:
        for split,features_key,kinds_key in (('training','x','training_kind'),('validation','vx','validation_kind')):
            kinds=stored[kinds_key];windows=stored[features_key]
            for kind in np.unique(kinds):
                indices=np.flatnonzero(kinds==kind)
                indices=rng.choice(indices,min(64,len(indices)),replace=False)
                samples.append(windows[indices].copy())
                groups.append((split,str(kind),len(indices)))
            del windows
    windows=np.concatenate(samples);del samples
    model=mixednet.model(flags,windows.shape[1:],None)
    model.load_weights(args.directory/'best.weights.h5')
    scores=model.predict(windows,batch_size=64,verbose=0).reshape(-1)
    report=[];offset=0
    for split,kind,count in groups:
        values=scores[offset:offset+count];offset+=count
        report.append({'split':split,'kind':kind,'samples':count,
            'mean_score':float(values.mean()),'accept_rate_at_05':float((values>=.5).mean()),
            'score_percentiles':np.percentile(values,[0,25,50,75,100]).tolist()})
    print(json.dumps({'read_only':True,'sampling_seed':4139,'synthetic_only':True,'groups':report}),flush=True)

if __name__=='__main__':main()
