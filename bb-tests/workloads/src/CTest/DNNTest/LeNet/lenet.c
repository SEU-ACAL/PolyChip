#include "dnn.h"
#include "lenet_params.h"
#include <stdio.h>

static dnn_i32 input[28 * 28];
static dnn_i32 conv1_w[6 * 1 * 5 * 5];
static dnn_i32 conv1_b[6];
static dnn_i32 conv2_w[16 * 6 * 5 * 5];
static dnn_i32 conv2_b[16];
static dnn_i32 fc1_w[120 * 256];
static dnn_i32 fc1_b[120];
static dnn_i32 fc2_w[84 * 120];
static dnn_i32 fc2_b[84];
static dnn_i32 fc3_w[10 * 84];
static dnn_i32 fc3_b[10];

static dnn_i32 conv1_out[6 * 24 * 24];
static dnn_i32 pool1_out[6 * 12 * 12];
static dnn_i32 conv2_out[16 * 8 * 8];
static dnn_i32 pool2_out[16 * 4 * 4];
static dnn_i32 fc1_out[120];
static dnn_i32 fc2_out[84];
static dnn_i32 logits[10];

static void load_weights(void) {
  const dnn_i32 *p = dnntest_lenet_params;
  int o = 0;

  for (int i = 0; i < 6 * 1 * 5 * 5; ++i) {
    conv1_w[i] = p[o++];
  }
  for (int i = 0; i < 6; ++i) {
    conv1_b[i] = p[o++];
  }
  for (int i = 0; i < 16 * 6 * 5 * 5; ++i) {
    conv2_w[i] = p[o++];
  }
  for (int i = 0; i < 16; ++i) {
    conv2_b[i] = p[o++];
  }
  for (int i = 0; i < 120 * 256; ++i) {
    fc1_w[i] = p[o++];
  }
  for (int i = 0; i < 120; ++i) {
    fc1_b[i] = p[o++];
  }
  for (int i = 0; i < 84 * 120; ++i) {
    fc2_w[i] = p[o++];
  }
  for (int i = 0; i < 84; ++i) {
    fc2_b[i] = p[o++];
  }
  for (int i = 0; i < 10 * 84; ++i) {
    fc3_w[i] = p[o++];
  }
  for (int i = 0; i < 10; ++i) {
    fc3_b[i] = p[o++];
  }
}

static void load_input(void) {
  for (int i = 0; i < 28 * 28; ++i) {
    input[i] = ((i * 7) % 255) - 127;
  }
}

dnn_res dnntest_lenet(void) {
  dnn_res r = {-1, 0};

  if (DNNTEST_LENET_PARAM_COUNT != 44426u ||
      DNNTEST_LENET_PARAM_EMBEDDED != 44426u) {
    printf("DNNTest LeNet FAILED bad params count=%u embedded=%u\n",
           DNNTEST_LENET_PARAM_COUNT, DNNTEST_LENET_PARAM_EMBEDDED);
    return r;
  }
  if (!dnn_any_nonzero(dnntest_lenet_params, DNNTEST_LENET_PARAM_EMBEDDED)) {
    printf("DNNTest LeNet FAILED empty params\n");
    return r;
  }

  load_input();
  load_weights();

  dnn_conv2d_valid_relu(input, 1, 28, 28, conv1_w, conv1_b, 6, 5, 5, conv1_out);
  dnn_scale_relu(conv1_out, 6 * 24 * 24, 128);
  dnn_maxpool2x2(conv1_out, 6, 24, 24, pool1_out);
  dnn_conv2d_valid_relu(pool1_out, 6, 12, 12, conv2_w, conv2_b, 16, 5, 5,
                        conv2_out);
  dnn_scale_relu(conv2_out, 16 * 8 * 8, 128);
  dnn_maxpool2x2(conv2_out, 16, 8, 8, pool2_out);
  dnn_dense(pool2_out, 16 * 4 * 4, fc1_w, fc1_b, 120, fc1_out);
  dnn_scale_relu(fc1_out, 120, 128);
  dnn_dense(fc1_out, 120, fc2_w, fc2_b, 84, fc2_out);
  dnn_scale_relu(fc2_out, 84, 128);
  dnn_dense(fc2_out, 84, fc3_w, fc3_b, 10, logits);
  dnn_scale(logits, 10, 128);

  r.cls = dnn_argmax(logits, 10);
  r.ok = 1;
  return r;
}
