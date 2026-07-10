#include "dnn.h"
#include "mobilenet_params.h"
#include <stdio.h>

#define MOB_IN_C 3
#define MOB_IN_H 12
#define MOB_IN_W 12
#define MOB_CONV_OC 8
#define MOB_PW_OC 4
#define MOB_CLASSES 3

static dnn_i32 input[MOB_IN_C * MOB_IN_H * MOB_IN_W];
static dnn_i32 conv_w[MOB_CONV_OC * MOB_IN_C * 3 * 3];
static dnn_i32 conv_b[MOB_CONV_OC];
static dnn_i32 conv_out[MOB_CONV_OC * 10 * 10];
static dnn_i32 point_w[MOB_PW_OC * MOB_CONV_OC];
static dnn_i32 point_b[MOB_PW_OC];
static dnn_i32 point_out[MOB_PW_OC * 10 * 10];
static dnn_i32 sums[MOB_PW_OC];
static dnn_i32 fc_w[MOB_CLASSES * MOB_PW_OC];
static dnn_i32 fc_b[MOB_CLASSES];
static dnn_i32 logits[MOB_CLASSES];

static void load_weights(void) {
  const dnn_i32 *p = dnntest_mobilenet_params;
  int o = 0;

  for (int i = 0; i < MOB_CONV_OC * MOB_IN_C * 3 * 3; ++i) {
    conv_w[i] = p[o++];
  }
  o = 16 * 3 * 3 * 3;
  for (int i = 0; i < MOB_CONV_OC; ++i) {
    conv_b[i] = p[o + i];
  }
  o += 128;
  for (int i = 0; i < MOB_PW_OC * MOB_CONV_OC; ++i) {
    point_w[i] = p[o + i];
  }
  o += MOB_PW_OC * MOB_CONV_OC;
  for (int i = 0; i < MOB_PW_OC; ++i) {
    point_b[i] = p[o + i];
  }
  o += 256;
  for (int i = 0; i < MOB_CLASSES * MOB_PW_OC; ++i) {
    fc_w[i] = p[o + i];
  }
  o += MOB_CLASSES * MOB_PW_OC;
  for (int i = 0; i < MOB_CLASSES; ++i) {
    fc_b[i] = p[o + i];
  }
}

static void load_input(void) {
  for (int i = 0; i < MOB_IN_C * MOB_IN_H * MOB_IN_W; ++i) {
    input[i] = ((i * 13 + 3) % 255) - 127;
  }
}

dnn_res dnntest_mobilenet(void) {
  dnn_res r = {-1, 0};

  if (DNNTEST_MOBILENET_PARAM_COUNT < 1000000u ||
      DNNTEST_MOBILENET_PARAM_EMBEDDED < 12000u) {
    printf("DNNTest MobileNet FAILED bad params count=%u embedded=%u\n",
           DNNTEST_MOBILENET_PARAM_COUNT, DNNTEST_MOBILENET_PARAM_EMBEDDED);
    return r;
  }
  if (!dnn_any_nonzero(dnntest_mobilenet_params,
                       DNNTEST_MOBILENET_PARAM_EMBEDDED)) {
    printf("DNNTest MobileNet FAILED empty params\n");
    return r;
  }

  load_input();
  load_weights();

  dnn_conv2d_valid_relu(input, MOB_IN_C, MOB_IN_H, MOB_IN_W, conv_w, conv_b,
                        MOB_CONV_OC, 3, 3, conv_out);
  dnn_scale_relu(conv_out, MOB_CONV_OC * 10 * 10, 128);
  dnn_pointwise_relu(conv_out, MOB_CONV_OC, 10, 10, point_w, point_b, MOB_PW_OC,
                     point_out);
  dnn_scale_relu(point_out, MOB_PW_OC * 10 * 10, 128);
  dnn_channel_sum(point_out, MOB_PW_OC, 10, 10, sums);
  dnn_dense(sums, MOB_PW_OC, fc_w, fc_b, MOB_CLASSES, logits);
  dnn_scale(logits, MOB_CLASSES, 128);

  r.cls = dnn_argmax(logits, MOB_CLASSES);
  r.ok = 1;
  return r;
}
