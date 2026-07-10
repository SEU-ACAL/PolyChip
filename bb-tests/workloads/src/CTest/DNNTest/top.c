#include "dnn.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

typedef dnn_res (*run_fn)(void);

typedef struct {
  const char *name;
  run_fn run;
} dnn_case;

static const dnn_case cases[] = {
    {"LeNet", dnntest_lenet},
    {"ResNet", dnntest_resnet},
    {"MobileNet", dnntest_mobilenet},
};

static inline uint64_t rdcycle(void) {
  unsigned long v;
  __asm__ volatile("csrr %0, cycle" : "=r"(v));
  return v;
}

int main(void) {
  int failures = 0;
  uint64_t total = 0;
  unsigned long n = sizeof(cases) / sizeof(cases[0]);

  printf("DNNTest top: %lu models\n", n);
  for (unsigned long i = 0; i < n; ++i) {
    const dnn_case *c = &cases[i];

    printf("DNNTest %s start\n", c->name);
    uint64_t start = rdcycle();
    dnn_res r = c->run();
    uint64_t cycles = rdcycle() - start;
    total += cycles;

    printf("DNNTest %-9s cycles=%lu class=%d %s\n", c->name,
           (unsigned long)cycles, r.cls, r.ok ? "PASS" : "FAIL");
    if (!r.ok) {
      failures++;
    }
  }

  printf("DNNTest total cycles=%lu failures=%d\n", (unsigned long)total,
         failures);
  exit(failures == 0 ? 0 : 1);
}
