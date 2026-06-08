set(ELF_CC "riscv64-unknown-elf-gcc")

set(CTEST_CHIPYARD_WORKLOAD_DIR ${CTEST_WORKLOAD_DIR}/chipyard)
set(BBSIM_LD ${BBSW_BAREMETAL_DIR}/bbsim.ld)
set(CHIPYARD_C_FLAGS
  -g -fno-common -O2 -static
  -march=rv64gc -mcmodel=medany
  -fno-builtin-printf -specs=nano.specs -specs=nosys.specs -nostartfiles
  -Wl,-T,${BBSIM_LD}
  -I${WORKLOAD_LIB_DIR}
  -I${CTEST_TOY_WORKLOAD_DIR}
  -I${CTEST_CHIPYARD_WORKLOAD_DIR}
)

function(add_chipyard_batch_matmul_test_target TEST_NAME SOURCE_FILE ACTIVE_HARTS)
  set(EXECUTABLE "${TEST_NAME}_${ACTIVE_HARTS}core-baremetal")

  add_custom_command(
    OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/${EXECUTABLE}
    COMMAND ${ELF_CC} ${CHIPYARD_C_FLAGS}
      -DACTIVE_HARTS=${ACTIVE_HARTS}
      -o ${EXECUTABLE}
      ${BBSW_BAREMETAL_DIR}/start.S
      ${CTEST_TOY_WORKLOAD_DIR}/buckyball.c
      ${CTEST_CHIPYARD_WORKLOAD_DIR}/${SOURCE_FILE}
    DEPENDS
      ${CTEST_CHIPYARD_WORKLOAD_DIR}/${SOURCE_FILE}
      ${BBSW_BAREMETAL_DIR}/start.S
      ${CTEST_TOY_WORKLOAD_DIR}/buckyball.c
    COMMENT "Building chipyard batch matmul ${ACTIVE_HARTS}-hart baremetal: ${EXECUTABLE}"
    WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
  )

  add_custom_target(${TEST_NAME}_${ACTIVE_HARTS}core_baremetal
    DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/${EXECUTABLE})
endfunction()

add_chipyard_batch_matmul_test_target(ctest_chipyard_batch_matmul batch_matmul.c 2)
add_chipyard_batch_matmul_test_target(ctest_chipyard_batch_matmul batch_matmul.c 4)
add_chipyard_batch_matmul_test_target(ctest_chipyard_batch_matmul batch_matmul.c 8)
add_chipyard_batch_matmul_test_target(ctest_chipyard_batch_matmul batch_matmul.c 16)
add_chipyard_batch_matmul_test_target(ctest_chipyard_batch_matmul batch_matmul.c 32)

add_custom_target(buckyball-chipyard-CTest-build ALL
  DEPENDS
    ctest_chipyard_batch_matmul_2core_baremetal
    ctest_chipyard_batch_matmul_4core_baremetal
    ctest_chipyard_batch_matmul_8core_baremetal
    ctest_chipyard_batch_matmul_16core_baremetal
    ctest_chipyard_batch_matmul_32core_baremetal
  COMMENT "Building all Chipyard comparison workloads"
  VERBATIM
)
