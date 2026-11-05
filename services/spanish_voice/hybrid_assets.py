"""Verify and copy native libraries onto an executable private runtime volume."""
import ctypes
import gc
import hashlib
from pathlib import Path
import platform
import shutil

from hybrid_t3 import HybridT3


def install(model,root,profile,profile_id,runtime):
    if platform.machine().lower() not in ('x86_64','amd64'):
        raise RuntimeError('This native voice build requires the original x86 NAS')
    cpu=Path('/proc/cpuinfo').read_text()
    if 'avx2' not in cpu or 'fma' not in cpu:
        raise RuntimeError('This native voice build requires AVX2 and FMA')
    engine=Path(runtime)/'native-engines'/profile_id;engine.mkdir(parents=True,exist_ok=True)
    libraries=profile['native_libraries']
    if not libraries or len(libraries)>16:raise ValueError('Invalid native library manifest')
    for name in libraries:
        if Path(name).name!=name or name not in profile['files']:raise ValueError('Invalid native library path')
        target=engine/name
        valid=False
        if target.is_file():
            with target.open('rb') as source:valid=hashlib.file_digest(source,'sha256').hexdigest()==profile['files'][name]
        if not valid:
            temporary=target.with_suffix(target.suffix+'.partial')
            shutil.copyfile(root/name,temporary);temporary.chmod(0o700)
            with temporary.open('rb') as source:
                if hashlib.file_digest(source,'sha256').hexdigest()!=profile['files'][name]:
                    raise ValueError('Copied native library integrity mismatch')
            temporary.replace(target)
    # Resolve dependencies explicitly: the immutable source bind may be mounted
    # noexec, and build-time RUNPATHs do not exist in this serving container.
    dependencies=[]
    for stem in ('libggml-base','libggml-cpu','libggml'):
        name=next((n for n in libraries if n==stem+'.so'),None)
        if name:dependencies.append(ctypes.CDLL(str(engine/name),mode=ctypes.RTLD_GLOBAL))
    adapter=HybridT3(engine/'libmochi-t3.so',root/profile['native_checkpoint'],
        model.conds.t3,model.t3.hp,seed=profile['seed'],threads=profile.get('t3_threads',8))
    model.t3=adapter;gc.collect()
    adapter.dependencies=dependencies
    return adapter
