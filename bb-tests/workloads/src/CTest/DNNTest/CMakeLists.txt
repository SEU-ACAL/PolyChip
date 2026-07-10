set(ELF_CC "riscv64-unknown-elf-gcc")

set(CTEST_DNNTEST_WORKLOAD_DIR ${CTEST_WORKLOAD_DIR}/DNNTest)
set(DNNTEST_SUPPORT_DIR ${CTEST_DNNTEST_WORKLOAD_DIR}/support)
set(DNNTEST_PARAM_DIR ${CTEST_DNNTEST_WORKLOAD_DIR}/params)
set(BBSIM_LD ${BBSW_BAREMETAL_DIR}/bbsim.ld)

set(DNNTEST_SUPPORT_SOURCES
  ${DNNTEST_SUPPORT_DIR}/dnn.c
)

set(DNNTEST_MODEL_SOURCES
  ${CTEST_DNNTEST_WORKLOAD_DIR}/LeNet/lenet.c
  ${CTEST_DNNTEST_WORKLOAD_DIR}/ResNet/resnet.c
  ${CTEST_DNNTEST_WORKLOAD_DIR}/MobileNet/mobilenet.c
)

set(DNNTEST_PARAM_HEADERS
  ${DNNTEST_PARAM_DIR}/lenet_params.h
  ${DNNTEST_PARAM_DIR}/resnet_params.h
  ${DNNTEST_PARAM_DIR}/mobilenet_params.h
)

set(DNNTEST_C_FLAGS
  -g -fno-common -O2 -static -march=rv64gc -mcmodel=medany
  -fno-builtin-printf -specs=nano.specs -specs=nosys.specs -nostartfiles
  -Wl,-T,${BBSIM_LD}
  -I${WORKLOAD_LIB_DIR}
  -I${DNNTEST_SUPPORT_DIR}
  -I${DNNTEST_PARAM_DIR}
  -ffunction-sections -fdata-sections
  -Wl,--gc-sections
)

set(DNNTEST_TOP_EXECUTABLE "dnntest_top_singlecore-baremetal")

add_custom_command(
  OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/${DNNTEST_TOP_EXECUTABLE}
  COMMAND ${ELF_CC} ${DNNTEST_C_FLAGS} -o ${DNNTEST_TOP_EXECUTABLE}
    ${BBSW_BAREMETAL_DIR}/crt0.S
    ${BBSW_BAREMETAL_DIR}/syscalls.c
    ${DNNTEST_SUPPORT_SOURCES}
    ${DNNTEST_MODEL_SOURCES}
    ${CTEST_DNNTEST_WORKLOAD_DIR}/top.c
    -lm
  DEPENDS
    ${DNNTEST_SUPPORT_SOURCES}
    ${DNNTEST_MODEL_SOURCES}
    ${DNNTEST_PARAM_HEADERS}
    ${CTEST_DNNTEST_WORKLOAD_DIR}/top.c
    ${BBSW_BAREMETAL_DIR}/crt0.S
    ${BBSW_BAREMETAL_DIR}/syscalls.c
  COMMENT "Building DNNTest top singlecore: ${DNNTEST_TOP_EXECUTABLE}"
  WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
)

add_custom_target(dnntest_top_singlecore_baremetal
  DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/${DNNTEST_TOP_EXECUTABLE})

add_custom_target(dnntest-all DEPENDS
  dnntest_top_singlecore_baremetal
  COMMENT "Building all DNNTest workloads"
)
