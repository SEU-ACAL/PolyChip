#include "dnn.h"
#include "resnet_params.h"
#include <stdio.h>

#define RESNET_OC 8
#define RESNET_IN_C 3
#define RESNET_IN_H 16
#define RESNET_IN_W 16
#define RESNET_K 7
#define RESNET_OUT_H 10
#define RESNET_OUT_W 10
#define RESNET_CLASSES 3

static dnn_i32 input[RESNET_IN_C * RESNET_IN_H * RESNET_IN_W];
static dnn_i32 conv_w[RESNET_OC * RESNET_IN_C * RESNET_K * RESNET_K];
static dnn_i32 conv_b[RESNET_OC];
static dnn_i32 conv_out[RESNET_OC * RESNET_OUT_H * RESNET_OUT_W];
static dnn_i32 sums[RESNET_OC];
static dnn_i32 fc_w[RESNET_CLASSES * RESNET_OC];
static dnn_i32 fc_b[RESNET_CLASSES];
static dnn_i32 logits[RESNET_CLASSES];

static void load_weights(void) {
  const dnn_i32 *p = dnntest_resnet_params;
  int o = 0;

  for (int i = 0; i < RESNET_OC * RESNET_IN_C * RESNET_K * RESNET_K; ++i) {
    conv_w[i] = p[o++];
  }
  o = 64 * 3 * 7 * 7;
  for (int i = 0; i < RESNET_OC; ++i) {
    conv_b[i] = p[o + i];
  }
  o += 512;
  for (int i = 0; i < RESNET_CLASSES * RESNET_OC; ++i) {
    fc_w[i] = p[o + i];
  }
  o += RESNET_CLASSES * RESNET_OC;
  for (int i = 0; i < RESNET_CLASSES; ++i) {
    fc_b[i] = p[o + i];
  }
}

static void load_input(void) {
  for (int i = 0; i < RESNET_IN_C * RESNET_IN_H * RESNET_IN_W; ++i) {
    input[i] = ((i * 5 + 11) % 255) - 127;
  }
}

dnn_res dnntest_resnet(void) {
  dnn_res r = {-1, 0};

  if (DNNTEST_RESNET_PARAM_COUNT < 10000000u ||
      DNNTEST_RESNET_PARAM_EMBEDDED < 12000u) {
    printf("DNNTest ResNet FAILED bad params count=%u embedded=%u\n",
           DNNTEST_RESNET_PARAM_COUNT, DNNTEST_RESNET_PARAM_EMBEDDED);
    return r;
  }
  if (!dnn_any_nonzero(dnntest_resnet_params, DNNTEST_RESNET_PARAM_EMBEDDED)) {
    printf("DNNTest ResNet FAILED empty params\n");
    return r;
  }

  load_input();
  load_weights();

  dnn_conv2d_valid_relu(input, RESNET_IN_C, RESNET_IN_H, RESNET_IN_W, conv_w,
                        conv_b, RESNET_OC, RESNET_K, RESNET_K, conv_out);
  dnn_scale_relu(conv_out, RESNET_OC * RESNET_OUT_H * RESNET_OUT_W, 128);
  dnn_channel_sum(conv_out, RESNET_OC, RESNET_OUT_H, RESNET_OUT_W, sums);
  dnn_dense(sums, RESNET_OC, fc_w, fc_b, RESNET_CLASSES, logits);
  dnn_scale(logits, RESNET_CLASSES, 128);

  r.cls = dnn_argmax(logits, RESNET_CLASSES);
  r.ok = 1;
  return r;
}
