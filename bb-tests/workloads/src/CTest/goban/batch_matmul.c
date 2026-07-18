#include "goban.h"
#include "scu.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#define DIM 16
#define TASKS 32
#define READY_PASS 1U
#define READY_FAIL 2U
#define READY_TIMEOUT 0x4000000U

#ifndef NTILES
#define NTILES 1
#endif

#ifndef NCORES
#define NCORES 4
#endif

#ifndef HIDDEN_HART_BASE
#define HIDDEN_HART_BASE NTILES
#endif

#ifndef TOTAL_HARTS
#define TOTAL_HARTS (NTILES * NCORES)
#endif

#if TASKS % NTILES != 0
#error "TASKS must be divisible by NTILES"
#endif

static inline uint64_t rdcycle64(void) {
  uint64_t cycles;
  asm volatile("rdcycle %0" : "=r"(cycles));
  return cycles;
}

static void wait_forever(void) {
  while (1) {
    asm volatile("wfi");
  }
}

static void sim_exit(int code) {
#if defined(__linux__)
  exit(code);
#else
  *(volatile uint32_t *)0x60000000 = (uint32_t)code;
  wait_forever();
#endif
}

static int expected_hart_id(int tile, int cid) {
  if (cid == 0) {
    return tile;
  }
  return HIDDEN_HART_BASE + tile * (NCORES - 1) + (cid - 1);
}

static void print_u64_scu(int hart, uint64_t value) {
  char buf[20];
  int n = 0;

  if (value == 0) {
    scu_putc(hart, '0');
    return;
  }

  while (value != 0) {
    buf[n++] = (char)('0' + (value % 10));
    value /= 10;
  }
  while (n > 0) {
    scu_putc(hart, buf[--n]);
  }
}

static inline int32_t aval(int job, int i, int k) { return (job + i + k) & 7; }

static inline int32_t bval(int job, int k, int j) {
  return (k == j) ? 1 : ((job + k + 2 * j) & 3);
}

static void matmul(int job, int32_t *out) {
  for (int i = 0; i < DIM; i++) {
    for (int j = 0; j < DIM; j++) {
      int32_t sum = 0;
      for (int k = 0; k < DIM; k++) {
        sum += aval(job, i, k) * bval(job, k, j);
      }
      out[i * DIM + j] = sum;
    }
  }
}

static int check(int job, int32_t *out) {
  for (int i = 0; i < DIM; i++) {
    for (int j = 0; j < DIM; j++) {
      int32_t exp = 0;
      for (int k = 0; k < DIM; k++) {
        exp += aval(job, i, k) * bval(job, k, j);
      }
      if (out[i * DIM + j] != exp) {
        return 1;
      }
    }
  }
  return 0;
}

static void print_progress(int hart, int job) {
  scu_puts(hart, "hart ");
  scu_put_u32(hart, (uint32_t)hart);
  scu_puts(hart, " test ");
  scu_put_u32(hart, (uint32_t)job);
  scu_puts(hart, " finished\n");
}

static void print_failure(int hart, int job) {
  scu_puts(hart, "hart ");
  scu_put_u32(hart, (uint32_t)hart);
  scu_puts(hart, " test ");
  scu_put_u32(hart, (uint32_t)job);
  scu_puts(hart, " FAILED\n");
}

static void print_summary_u32(const char *name, uint32_t value) {
  scu_puts(0, name);
  scu_put_u32(0, value);
  scu_puts(0, "\n");
}

static void mark_done(int hart, int failed) {
  scu_set_ready(hart, failed ? READY_FAIL : READY_PASS);
}

static int wait_all_harts_done(void) {
  for (uint32_t wait = 0; wait < READY_TIMEOUT; wait++) {
    int missing = -1;
    int any_failed = 0;
    for (int hart = 0; hart < TOTAL_HARTS; hart++) {
      uint8_t value = scu_get_ready(hart);
      if (value == READY_FAIL) {
        any_failed = 1;
      } else if (value != READY_PASS) {
        missing = hart;
        break;
      }
    }
    if (missing < 0) {
      return any_failed ? 0 : 1;
    }
    asm volatile("nop" ::: "memory");
  }
  return -1;
}

static void print_hart_cycles(int hart, uint64_t cycles) {
  scu_puts(hart, "BATCH_MATMUL_HART_CYCLES=");
  scu_put_u32(hart, (uint32_t)hart);
  scu_puts(hart, ",");
  print_u64_scu(hart, cycles);
  scu_puts(hart, "\n");
}

int main(void) {
  int hart = bb_get_hart_id();
  int tile = bb_get_tile_id();
  int cid = bb_get_tile_core_id();

  if (hart < 0 || hart >= TOTAL_HARTS || tile < 0 || tile >= NTILES ||
      cid < 0 || cid >= NCORES || hart != expected_hart_id(tile, cid)) {
    if (hart >= 0) {
      scu_puts(hart, "batch matmul invalid hart mapping\n");
    }
    wait_forever();
  }

  if (cid != 0) {
    mark_done(hart, 0);
    wait_forever();
  }

  int32_t out[DIM * DIM] __attribute__((aligned(64)));
  int tasks_per_tile = TASKS / NTILES;
  int first_job = tile * tasks_per_tile;
  uint64_t cycles = 0;
  int failed = 0;

  for (int i = 0; i < tasks_per_tile; i++) {
    int job = first_job + i;
    uint64_t begin = rdcycle64();
    matmul(job, out);
    uint64_t end = rdcycle64();
    cycles += end - begin;
    if (check(job, out) != 0) {
      failed = 1;
      print_failure(hart, job);
      break;
    }
    print_progress(hart, job);
  }

  print_hart_cycles(hart, cycles);
  mark_done(hart, failed);

  if (hart != 0) {
    wait_forever();
  }

  int done_status = wait_all_harts_done();
  if (done_status < 0) {
    scu_puts(0, "batch matmul ready timeout\n");
    sim_exit(1);
  }

  if (done_status == 0) {
    sim_exit(1);
  }

  print_summary_u32("BATCH_MATMUL_ACTIVE_HARTS=", TOTAL_HARTS);
  print_summary_u32("BATCH_MATMUL_TASKS=", TASKS);
  print_summary_u32("BATCH_MATMUL_TASKS_PER_HART=", TASKS / NTILES);
  scu_puts(0, "BATCH_MATMUL_CYCLES=");
  print_u64_scu(0, cycles);
  scu_puts(0, "\n");
  scu_puts(0, "batch matmul PASSED\n");
  sim_exit(0);
}
