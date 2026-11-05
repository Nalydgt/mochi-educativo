"""Apply the reviewed HTTP cancellation guard in memory on each catalog startup."""
from __future__ import annotations

import hashlib
import importlib.abc
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import sys

TARGET_MODULE='gateway.platforms.api_server_openai_routes'
PATCHED_SHA256='44f7886ceb6d5a4e6ca7af617e92299589cb92724d4df723aa1d32cf45557ccd'
LOADED_DIR=Path(__file__).with_name('loaded')
PROCESS_STAT=Path('/proc/self/stat')


def _recipe():
    path=Path(__file__).with_name('patch.py')
    spec=importlib.util.spec_from_file_location('_mochi_hermes_disconnect_recipe',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def runtime_source(raw):
    recipe=_recipe()
    digest=hashlib.sha256(raw).hexdigest()
    if digest==PATCHED_SHA256:return raw,digest
    if digest!=recipe.SUPPORTED_SOURCE_SHA256:
        raise ImportError('Mochi Hermes HTTP cancellation guard: unreviewed API source; review this image before serving turns')
    effective=recipe.patched_source(raw)
    if hashlib.sha256(effective).hexdigest()!=PATCHED_SHA256:
        raise ImportError('Mochi Hermes HTTP cancellation guard: reviewed recipe integrity mismatch')
    return effective,digest


class ReviewedSourceLoader(importlib.machinery.SourceFileLoader):
    def get_code(self,fullname):
        # Compile the reviewed source, never an image's pre-existing .pyc.
        raw=Path(self.path).read_bytes()
        effective,self.source_sha256=runtime_source(raw)
        self.effective_sha256=hashlib.sha256(effective).hexdigest()
        return compile(effective,self.path,'exec',dont_inherit=True)

    def exec_module(self,module):
        super().exec_module(module)
        stat=PROCESS_STAT.read_text()
        ticks=stat[stat.rfind(')')+2:].split()[19]
        marker={'pid':os.getpid(),'process_start_ticks':ticks,'module':self.name,
                'source_sha256':self.source_sha256,'effective_sha256':self.effective_sha256}
        LOADED_DIR.mkdir(mode=0o770,parents=True,exist_ok=True)
        path=LOADED_DIR/(str(os.getpid())+'-'+ticks+'.json')
        temporary=path.with_suffix('.partial')
        temporary.write_text(json.dumps(marker,sort_keys=True)+'\n')
        os.replace(temporary,path)


class ReviewedSourceFinder(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname!=TARGET_MODULE:return None
        spec=importlib.machinery.PathFinder.find_spec(fullname,path,target)
        if spec is None or not isinstance(spec.loader,importlib.machinery.SourceFileLoader):
            raise ImportError('Mochi Hermes HTTP cancellation guard: unsupported API module loader')
        spec.loader=ReviewedSourceLoader(fullname,spec.origin)
        return spec


def install():
    if not any(isinstance(finder,ReviewedSourceFinder) for finder in sys.meta_path):
        sys.meta_path.insert(0,ReviewedSourceFinder())
