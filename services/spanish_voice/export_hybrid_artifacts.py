"""Export verified native artifacts to the NAS staging bind, without selecting them."""
import hashlib
import json
from pathlib import Path
import shutil

root=Path('/compile/cpp-v1');output=Path('/results/hybrid-v1')
parity=json.loads((output/'parity.json').read_text())
report=json.loads((output/'report.json').read_text())
threads=json.loads((output/'decoder-threads.json').read_text())
if not parity['passed'] or len(report)!=4:raise RuntimeError('The native trial is incomplete')
eligible=[row for row in threads if row['waveform_cosine']>.9999]
if not eligible:raise RuntimeError('No decoder thread count preserved the waveform')
best=min(eligible,key=lambda row:row['seconds'])['threads']
assets=output/'artifacts';assets.mkdir(exist_ok=True)
sources={'t3-ggml-q8.gguf':root/'t3-q8_0.gguf','libmochi-t3.so':root/'build/libmochi-t3.so',
    'chatterbox-cpp-LICENSE.txt':root/'source/LICENSE','ggml-LICENSE.txt':root/'source/ggml/LICENSE'}
for path in (root/'build/ggml').rglob('libggml*.so*'):
    if path.is_file():sources[path.name]=path
files={}
for name,path in sources.items():
    temporary=assets/(name+'.partial');shutil.copyfile(path,temporary)
    with temporary.open('rb') as source:files[name]=hashlib.file_digest(source,'sha256').hexdigest()
    temporary.replace(assets/name)
profile=json.loads(Path('/assets/profile.json').read_text())
metadata={'schema':1,'cpp_revision':'ddca05fb69c2910b0d7b5eae420d360ed98c067b',
    'ggml_revision':'58c3805840b516b2a88ff867ccf7bb41dba79951','numerical_parity_passed':True,
    'native_libraries':sorted(name for name in files if '.so' in name),
    'decoder_threads':best,'t3_threads':8,'files':files,
    'source_checkpoint_sha256':profile['files'][profile['checkpoint']],
    'reference_sha256':profile['files']['reference.wav'],
    'adapter_sha256':hashlib.sha256(Path('/app/hybrid_t3.cpp').read_bytes()).hexdigest(),
    'python_adapter_sha256':hashlib.sha256(Path('/app/hybrid_t3.py').read_bytes()).hexdigest(),
    'production_selected':False}
(output/'artifacts.json').write_text(json.dumps(metadata,indent=2))
print(json.dumps({'artifacts_staged':True,'decoder_threads':best,'production_selected':False}),flush=True)
