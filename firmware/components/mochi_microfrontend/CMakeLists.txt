set(frontend tensorflow/lite/experimental/microfrontend/lib)
set(srcs kiss_fft_int16.cc fft.cc fft_util.cc filterbank.cc filterbank_util.cc
    frontend.cc frontend_util.cc log_lut.cc log_scale.cc log_scale_util.cc
    noise_reduction.cc noise_reduction_util.cc pcan_gain_control.cc
    pcan_gain_control_util.cc window.cc window_util.cc)
list(TRANSFORM srcs PREPEND "${frontend}/")
idf_component_register(SRCS ${srcs} kissfft/kiss_fft.cc kissfft/tools/kiss_fftr.cc INCLUDE_DIRS . kissfft)
target_compile_definitions(${COMPONENT_LIB} PRIVATE FIXED_POINT=16)
target_compile_options(${COMPONENT_LIB} PRIVATE -Wno-error=unused-function -Wno-error=unused-variable)
