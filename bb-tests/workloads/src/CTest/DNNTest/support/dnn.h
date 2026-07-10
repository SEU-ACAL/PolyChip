#ifndef DNNTEST_DNN_H
#define DNNTEST_DNN_H

#include <stdint.h>

typedef int32_t dnn_i32;

typedef struct {
  int cls;
  int ok;
} dnn_res;

void dnn_conv2d_valid_relu(const dnn_i32 *in, int in_c, int in_h, int in_w,
                           const dnn_i32 *w, const dnn_i32 *b, int out_c,
                           int k_h, int k_w, dnn_i32 *out);
void dnn_conv2d_same_relu(const dnn_i32 *in, int in_c, int h, int in_w,
                          const dnn_i32 *w, const dnn_i32 *b, int out_c,
                          int k_h, int k_w, dnn_i32 *out);
void dnn_depthwise_valid_relu(const dnn_i32 *in, int c, int in_h, int in_w,
                              const dnn_i32 *w, const dnn_i32 *b, int k_h,
                              int k_w, dnn_i32 *out);
void dnn_pointwise_relu(const dnn_i32 *in, int in_c, int h, int in_w,
                        const dnn_i32 *w, const dnn_i32 *b, int out_c,
                        dnn_i32 *out);
void dnn_maxpool2x2(const dnn_i32 *in, int c, int in_h, int in_w, dnn_i32 *out);
void dnn_dense(const dnn_i32 *in, int in_n, const dnn_i32 *w, const dnn_i32 *b,
               int out_n, dnn_i32 *out);
void dnn_channel_sum(const dnn_i32 *in, int c, int h, int in_w, dnn_i32 *out);
int dnn_argmax(const dnn_i32 *x, int n);
int dnn_check(const char *name, const dnn_i32 *got, const dnn_i32 *exp, int n);

void dnn_scale_relu(dnn_i32 *x, int n, int scale);
void dnn_scale(dnn_i32 *x, int n, int scale);
int dnn_any_nonzero(const dnn_i32 *x, int n);

dnn_res dnntest_lenet(void);
dnn_res dnntest_resnet(void);
dnn_res dnntest_mobilenet(void);

#endif
