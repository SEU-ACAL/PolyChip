set(ELF_CC "riscv64-unknown-elf-gcc")

#-------------------------------------------------------------------------------
# Goban: multi-core (SPMD) baremetal workloads
# All cores run the ELF simultaneously; divergence is by mhartid.
#-------------------------------------------------------------------------------
set(CTEST_GOBAN_WORKLOAD_DIR ${CTEST_WORKLOAD_DIR}/goban)
set(GOBAN_LD ${CTEST_GOBAN_WORKLOAD_DIR}/goban.ld)

set(GOBAN_C_FLAGS
  -g -fno-common -O2 -static
  -march=rv64gc -mcmodel=medany
  -fno-builtin-printf -specs=nano.specs -specs=nosys.specs -nostartfiles
  -Wl,-T,${GOBAN_LD}
  -I${WORKLOAD_LIB_DIR}
  -I${CTEST_GOBAN_WORKLOAD_DIR}
)

# Generate a multicore baremetal ELF.
# start.S (goban version) launches all harts into main().
function(add_goban_test_target TEST_NAME SOURCE_FILE)
  set(EXECUTABLE "${TEST_NAME}_multicore-baremetal")

  add_custom_command(
    OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/${EXECUTABLE}
    COMMAND ${ELF_CC} ${GOBAN_C_FLAGS}
      -o ${EXECUTABLE}
      ${CTEST_GOBAN_WORKLOAD_DIR}/start.S
      ${CTEST_GOBAN_WORKLOAD_DIR}/${SOURCE_FILE}
    DEPENDS
      ${CTEST_GOBAN_WORKLOAD_DIR}/${SOURCE_FILE}
      ${CTEST_GOBAN_WORKLOAD_DIR}/start.S
      ${CTEST_GOBAN_WORKLOAD_DIR}/goban.h
      ${CTEST_GOBAN_WORKLOAD_DIR}/scu.h
    COMMENT "Building goban multicore baremetal: ${EXECUTABLE}"
    WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
  )

  add_custom_target(${TEST_NAME}
    DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/${EXECUTABLE}
    COMMENT "Building ${TEST_NAME}"
  )
endfunction()

function(add_goban_64t4c_test_target TEST_NAME SOURCE_FILE)
  set(EXECUTABLE "${TEST_NAME}_multicore-baremetal")

  add_custom_command(
    OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/${EXECUTABLE}
    COMMAND ${ELF_CC} ${GOBAN_C_FLAGS}
      -DGOBAN_MAX_TILES=64
      -DGOBAN_HIDDEN_HART_BASE=64
      -DGOBAN_STACK_TOP=0x80400000
      -o ${EXECUTABLE}
      ${CTEST_GOBAN_WORKLOAD_DIR}/start.S
      ${CTEST_GOBAN_WORKLOAD_DIR}/${SOURCE_FILE}
    DEPENDS
      ${CTEST_GOBAN_WORKLOAD_DIR}/${SOURCE_FILE}
      ${CTEST_GOBAN_WORKLOAD_DIR}/start.S
      ${CTEST_GOBAN_WORKLOAD_DIR}/goban.h
      ${CTEST_GOBAN_WORKLOAD_DIR}/scu.h
    COMMENT "Building goban 64t4c baremetal: ${EXECUTABLE}"
    WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
  )

  add_custom_target(${TEST_NAME}
    DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/${EXECUTABLE}
    COMMENT "Building ${TEST_NAME}"
  )
endfunction()

function(add_goban_2t4c_test_target TEST_NAME SOURCE_FILE)
  set(EXECUTABLE "${TEST_NAME}_multicore-baremetal")

  add_custom_command(
    OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/${EXECUTABLE}
    COMMAND ${ELF_CC} ${GOBAN_C_FLAGS}
      -DGOBAN_MAX_TILES=2
      -DGOBAN_HIDDEN_HART_BASE=2
      -DNTILES=2
      -DHIDDEN_HART_BASE=2
      -o ${EXECUTABLE}
      ${CTEST_GOBAN_WORKLOAD_DIR}/start.S
      ${CTEST_GOBAN_WORKLOAD_DIR}/${SOURCE_FILE}
    DEPENDS
      ${CTEST_GOBAN_WORKLOAD_DIR}/${SOURCE_FILE}
      ${CTEST_GOBAN_WORKLOAD_DIR}/start.S
      ${CTEST_GOBAN_WORKLOAD_DIR}/goban.h
      ${CTEST_GOBAN_WORKLOAD_DIR}/scu.h
    COMMENT "Building goban 2t4c baremetal: ${EXECUTABLE}"
    WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
  )

  add_custom_target(${TEST_NAME}
    DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/${EXECUTABLE}
    COMMENT "Building ${TEST_NAME}"
  )
endfunction()

function(add_goban_batch_matmul_test_target TEST_NAME SOURCE_FILE TOTAL_HARTS ACTIVE_TILES CORES_PER_TILE)
  set(EXECUTABLE "${TEST_NAME}_${TOTAL_HARTS}core-baremetal")

  add_custom_command(
    OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/${EXECUTABLE}
    COMMAND ${ELF_CC} ${GOBAN_C_FLAGS}
      -DGOBAN_MAX_TILES=${ACTIVE_TILES}
      -DGOBAN_HIDDEN_HART_BASE=${ACTIVE_TILES}
      -DTOTAL_HARTS=${TOTAL_HARTS}
      -DNTILES=${ACTIVE_TILES}
      -DHIDDEN_HART_BASE=${ACTIVE_TILES}
      -DNCORES=${CORES_PER_TILE}
      -DGOBAN_STACK_TOP=0x80400000
      -o ${EXECUTABLE}
      ${CTEST_GOBAN_WORKLOAD_DIR}/start.S
      ${CTEST_GOBAN_WORKLOAD_DIR}/${SOURCE_FILE}
    DEPENDS
      ${CTEST_GOBAN_WORKLOAD_DIR}/${SOURCE_FILE}
      ${CTEST_GOBAN_WORKLOAD_DIR}/start.S
      ${CTEST_GOBAN_WORKLOAD_DIR}/goban.h
      ${CTEST_GOBAN_WORKLOAD_DIR}/scu.h
    COMMENT "Building goban batch matmul ${TOTAL_HARTS}-hart baremetal: ${EXECUTABLE}"
    WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
  )

  add_custom_target(${TEST_NAME}_${TOTAL_HARTS}core_baremetal
    DEPENDS ${CMAKE_CURRENT_BINARY_DIR}/${EXECUTABLE})
endfunction()

#-------------------------------------------------------------------------------
# Build list
#-------------------------------------------------------------------------------
add_goban_test_target(ctest_goban_barrier_test      barrier_test.c)
add_goban_test_target(ctest_goban_barrier_mvin_test barrier_mvin_test.c)
add_goban_2t4c_test_target(ctest_goban_hetero_2t4c_smoke_test hetero_64t4c_smoke_test.c)
add_goban_64t4c_test_target(ctest_goban_hetero_64t4c_smoke_test hetero_64t4c_smoke_test.c)
add_goban_2t4c_test_target(ctest_goban_uart_rx_echo_2t4c_test uart_rx_echo_test.c)
add_goban_64t4c_test_target(ctest_goban_uart_rx_echo_64t4c_test uart_rx_echo_test.c)
add_goban_batch_matmul_test_target(ctest_goban_batch_matmul batch_matmul.c 2 2 1)
add_goban_batch_matmul_test_target(ctest_goban_batch_matmul batch_matmul.c 4 4 1)
add_goban_batch_matmul_test_target(ctest_goban_batch_matmul batch_matmul.c 8 8 1)
add_goban_batch_matmul_test_target(ctest_goban_batch_matmul batch_matmul.c 16 16 1)
add_goban_batch_matmul_test_target(ctest_goban_batch_matmul batch_matmul.c 32 32 1)

# Master build target
add_custom_target(buckyball-goban-CTest-build ALL
  DEPENDS
    ctest_goban_barrier_test
    ctest_goban_barrier_mvin_test
    ctest_goban_hetero_2t4c_smoke_test
    ctest_goban_hetero_64t4c_smoke_test
    ctest_goban_uart_rx_echo_2t4c_test
    ctest_goban_uart_rx_echo_64t4c_test
    ctest_goban_batch_matmul_2core_baremetal
    ctest_goban_batch_matmul_4core_baremetal
    ctest_goban_batch_matmul_8core_baremetal
    ctest_goban_batch_matmul_16core_baremetal
    ctest_goban_batch_matmul_32core_baremetal
  COMMENT "Building all Goban workloads"
  VERBATIM
)
