#include <stdint.h>
#include <stdio.h>

#define DIM 16

static int32_t a[DIM * DIM] __attribute__((aligned(64)));
static int32_t b[DIM * DIM] __attribute__((aligned(64)));
static int32_t c[DIM * DIM] __attribute__((aligned(64)));

static inline uint64_t rdcycle64(void) {
  uint64_t cycles;
  asm volatile("rdcycle %0" : "=r"(cycles));
  return cycles;
}

static void init_mats(void) {
  for (int i = 0; i < DIM; i++) {
    for (int j = 0; j < DIM; j++) {
      a[i * DIM + j] = (i + j) & 7;
      b[i * DIM + j] = (i == j) ? 1 : ((i + 2 * j) & 3);
      c[i * DIM + j] = 0;
    }
  }
}

static void matmul(void) {
  for (int i = 0; i < DIM; i++) {
    for (int j = 0; j < DIM; j++) {
      int32_t sum = 0;
      for (int k = 0; k < DIM; k++) {
        sum += a[i * DIM + k] * b[k * DIM + j];
      }
      c[i * DIM + j] = sum;
    }
  }
}

static int check(void) {
  for (int i = 0; i < DIM; i++) {
    for (int j = 0; j < DIM; j++) {
      int32_t exp = 0;
      for (int k = 0; k < DIM; k++) {
        exp += a[i * DIM + k] * b[k * DIM + j];
      }
      if (c[i * DIM + j] != exp) {
        printf("batch matmul FAILED at (%d,%d): expected %d, got %d\n", i, j,
               exp, c[i * DIM + j]);
        return 1;
      }
    }
  }
  return 0;
}

int main(void) {
  init_mats();

  uint64_t begin = rdcycle64();
  matmul();
  uint64_t end = rdcycle64();

  if (check() != 0) {
    return 1;
  }

  printf("BATCH_MATMUL_CYCLES=%llu\n", (unsigned long long)(end - begin));
  printf("batch matmul PASSED\n");
  return 0;
}
