#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#define DIM 16
#define TASKS 32
#ifndef ACTIVE_HARTS
#define ACTIVE_HARTS 1
#endif

#if TASKS % ACTIVE_HARTS != 0
#error "TASKS must be divisible by ACTIVE_HARTS"
#endif

static inline uint64_t rdcycle64(void) {
  uint64_t cycles;
  asm volatile("rdcycle %0" : "=r"(cycles));
  return cycles;
}

static inline uint64_t mhartid(void) {
  uint64_t id;
  asm volatile("csrr %0, mhartid" : "=r"(id));
  return id;
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
  while (1) {
    asm volatile("wfi");
  }
#endif
}

static void print_u64(uint64_t val) {
  char buf[20];
  int len = 0;
  if (val == 0) {
    putchar('0');
    return;
  }
  while (val != 0) {
    buf[len++] = (char)('0' + (val % 10));
    val /= 10;
  }
  while (len != 0) {
    putchar(buf[--len]);
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
        printf("batch matmul FAILED at job %d (%d,%d): expected %d, got %d\n",
               job, i, j, exp, out[i * DIM + j]);
        return 1;
      }
    }
  }
  return 0;
}

static volatile uint64_t hart_cycles[ACTIVE_HARTS] __attribute__((aligned(64)));
static volatile uint32_t hart_done[ACTIVE_HARTS] __attribute__((aligned(64)));
static volatile uint32_t hart_status[ACTIVE_HARTS] __attribute__((aligned(64)));

int main(void) {
  uint64_t id = mhartid();
  if (id >= ACTIVE_HARTS) {
    wait_forever();
  }

  int32_t out[DIM * DIM] __attribute__((aligned(64)));
  int tasks_per_hart = TASKS / ACTIVE_HARTS;
  int first_job = (int)id * tasks_per_hart;
  uint64_t cycles = 0;
  int failed = 0;
  for (int i = 0; i < tasks_per_hart; i++) {
    int job = first_job + i;
    uint64_t begin = rdcycle64();
    matmul(job, out);
    uint64_t end = rdcycle64();
    cycles += end - begin;
    if (check(job, out) != 0) {
      failed = 1;
      break;
    }
  }

  hart_cycles[id] = cycles;
  hart_status[id] = (uint32_t)failed;
  __sync_synchronize();
  hart_done[id] = 1;

  if (id != 0) {
    wait_forever();
  }

  uint64_t max_cycles = 0;
  int any_failed = failed;
  for (int i = 0; i < ACTIVE_HARTS; i++) {
    while (hart_done[i] == 0) {
    }
    if (hart_status[i] != 0) {
      any_failed = 1;
    }
    if (hart_cycles[i] > max_cycles) {
      max_cycles = hart_cycles[i];
    }
  }
  if (any_failed) {
    sim_exit(1);
  }

  printf("BATCH_MATMUL_ACTIVE_HARTS=%u\n", ACTIVE_HARTS);
  printf("BATCH_MATMUL_TASKS=%u\n", TASKS);
  printf("BATCH_MATMUL_TASKS_PER_HART=%u\n", TASKS / ACTIVE_HARTS);
  printf("BATCH_MATMUL_CYCLES=");
  print_u64(max_cycles);
  printf("\n");
  printf("batch matmul PASSED\n");
  sim_exit(0);
}
