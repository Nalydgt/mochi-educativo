#!/bin/sh
set -eu
export PYTHONUNBUFFERED=1
export PYTHONPATH=/compile/python
export OMP_NUM_THREADS=8
mkdir -p /compile/python /compile/cpp-v1 /results/cpp-v1
/runtime/venv/bin/pip install --no-deps --target /compile/python 'gguf==0.17.1' >/results/cpp-v1/dependencies.log 2>&1
if ! test -d /compile/cpp-v1/source/.git; then
    git clone --quiet https://github.com/gianni-cor/chatterbox.cpp.git /compile/cpp-v1/source
    git -C /compile/cpp-v1/source checkout --quiet --detach ddca05fb69c2910b0d7b5eae420d360ed98c067b
fi
cd /compile/cpp-v1/source
if ! test -f ggml/.mochi-patched; then
    mkdir -p ggml
    git -C ggml init --quiet
    git -C ggml remote add origin https://github.com/ggml-org/ggml.git
    git -C ggml fetch --quiet --depth 1 origin 58c3805840b516b2a88ff867ccf7bb41dba79951
    git -C ggml checkout --quiet --detach 58c3805840b516b2a88ff867ccf7bb41dba79951
    git -C ggml apply ../patches/ggml-metal-chatterbox-ops.patch
    git -C ggml apply ../patches/ggml-opencl-chatterbox-ops.patch
    touch ggml/.mochi-patched
fi
cmake -S . -B /compile/cpp-v1/build -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=ON -DTTS_CPP_BUILD_TESTS=OFF >/results/cpp-v1/build.log 2>&1
cmake --build /compile/cpp-v1/build --target tts-cli -j4 >>/results/cpp-v1/build.log 2>&1
if test "${MOCHI_BENCH_MODE:-}" = hybrid; then
    MOCHI_CPP_PREPARE_ONLY=1 /runtime/venv/bin/python /app/cpp_trial.py
    /runtime/venv/bin/python - <<'PY'
from pathlib import Path
p=Path('/compile/cpp-v1/source/src/t3_mtl.cpp')
s=p.read_text()
marker='thread_local int mochi_speech_position_override'
if marker not in s:
    namespace='namespace tts_cpp::chatterbox::detail {'
    if s.count('int32_t sp = n_past;')!=2:raise RuntimeError('Unexpected upstream speech-position implementation')
    s=s.replace(namespace,namespace+'\nthread_local int mochi_speech_position_override=-1;\nvoid mochi_set_speech_position(int position) { mochi_speech_position_override=position; }',1)
    s=s.replace('int32_t sp = n_past;','int32_t sp = mochi_speech_position_override>=0 ? mochi_speech_position_override : n_past;')
    p.write_text(s)
p=Path('/compile/cpp-v1/source/CMakeLists.txt')
marker='# Mochi persistent multilingual adapter'
s=p.read_text()
if marker not in s:
    s+='\n'+marker+'''
add_library(mochi-t3 SHARED /app/hybrid_t3.cpp)
target_include_directories(mochi-t3 PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/src ${CMAKE_CURRENT_SOURCE_DIR}/ggml/include)
target_link_libraries(mochi-t3 PRIVATE tts-cpp ggml)
'''
    p.write_text(s)
PY
    cmake -S . -B /compile/cpp-v1/build -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=ON -DTTS_CPP_BUILD_TESTS=OFF >>/results/cpp-v1/build.log 2>&1
    cmake --build /compile/cpp-v1/build --target mochi-t3 -j4 >>/results/cpp-v1/build.log 2>&1
    /runtime/venv/bin/python /app/hybrid_trial.py
else
    echo 'Only the approved hybrid build is supported' >&2
    exit 2
fi
