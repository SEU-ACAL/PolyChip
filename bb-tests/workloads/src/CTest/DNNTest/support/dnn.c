#include "dnn.h"
#include <stdio.h>

static dnn_i32 relu(dnn_i32 x) { return x > 0 ? x : 0; }

void dnn_conv2d_valid_relu(const dnn_i32 *in, int in_c, int in_h, int in_w,
                           const dnn_i32 *w, const dnn_i32 *b, int out_c,
                           int k_h, int k_w, dnn_i32 *out) {
  int out_h = in_h - k_h + 1;
  int out_w = in_w - k_w + 1;

  for (int oc = 0; oc < out_c; ++oc) {
    for (int oy = 0; oy < out_h; ++oy) {
      for (int ox = 0; ox < out_w; ++ox) {
        dnn_i32 acc = b[oc];
        for (int ic = 0; ic < in_c; ++ic) {
          for (int ky = 0; ky < k_h; ++ky) {
            for (int kx = 0; kx < k_w; ++kx) {
              int in_idx = (ic * in_h + oy + ky) * in_w + ox + kx;
              int w_idx = ((oc * in_c + ic) * k_h + ky) * k_w + kx;
              acc += in[in_idx] * w[w_idx];
            }
          }
        }
        out[(oc * out_h + oy) * out_w + ox] = relu(acc);
      }
    }
  }
}

void dnn_conv2d_same_relu(const dnn_i32 *in, int in_c, int h, int in_w,
                          const dnn_i32 *w, const dnn_i32 *b, int out_c,
                          int k_h, int k_w, dnn_i32 *out) {
  int pad_y = k_h / 2;
  int pad_x = k_w / 2;

  for (int oc = 0; oc < out_c; ++oc) {
    for (int oy = 0; oy < h; ++oy) {
      for (int ox = 0; ox < in_w; ++ox) {
        dnn_i32 acc = b[oc];
        for (int ic = 0; ic < in_c; ++ic) {
          for (int ky = 0; ky < k_h; ++ky) {
            int iy = oy + ky - pad_y;
            if (iy < 0 || iy >= h) {
              continue;
            }
            for (int kx = 0; kx < k_w; ++kx) {
              int ix = ox + kx - pad_x;
              if (ix < 0 || ix >= in_w) {
                continue;
              }
              int in_idx = (ic * h + iy) * in_w + ix;
              int w_idx = ((oc * in_c + ic) * k_h + ky) * k_w + kx;
              acc += in[in_idx] * w[w_idx];
            }
          }
        }
        out[(oc * h + oy) * in_w + ox] = relu(acc);
      }
    }
  }
}

void dnn_depthwise_valid_relu(const dnn_i32 *in, int c, int in_h, int in_w,
                              const dnn_i32 *w, const dnn_i32 *b, int k_h,
                              int k_w, dnn_i32 *out) {
  int out_h = in_h - k_h + 1;
  int out_w = in_w - k_w + 1;

  for (int ch = 0; ch < c; ++ch) {
    for (int oy = 0; oy < out_h; ++oy) {
      for (int ox = 0; ox < out_w; ++ox) {
        dnn_i32 acc = b[ch];
        for (int ky = 0; ky < k_h; ++ky) {
          for (int kx = 0; kx < k_w; ++kx) {
            int in_idx = (ch * in_h + oy + ky) * in_w + ox + kx;
            int w_idx = (ch * k_h + ky) * k_w + kx;
            acc += in[in_idx] * w[w_idx];
          }
        }
        out[(ch * out_h + oy) * out_w + ox] = relu(acc);
      }
    }
  }
}

void dnn_pointwise_relu(const dnn_i32 *in, int in_c, int h, int in_w,
                        const dnn_i32 *w, const dnn_i32 *b, int out_c,
                        dnn_i32 *out) {
  for (int oc = 0; oc < out_c; ++oc) {
    for (int y = 0; y < h; ++y) {
      for (int x = 0; x < in_w; ++x) {
        dnn_i32 acc = b[oc];
        for (int ic = 0; ic < in_c; ++ic) {
          acc += in[(ic * h + y) * in_w + x] * w[oc * in_c + ic];
        }
        out[(oc * h + y) * in_w + x] = relu(acc);
      }
    }
  }
}

void dnn_maxpool2x2(const dnn_i32 *in, int c, int in_h, int in_w,
                    dnn_i32 *out) {
  int out_h = in_h / 2;
  int out_w = in_w / 2;

  for (int ch = 0; ch < c; ++ch) {
    for (int oy = 0; oy < out_h; ++oy) {
      for (int ox = 0; ox < out_w; ++ox) {
        dnn_i32 max = in[(ch * in_h + oy * 2) * in_w + ox * 2];
        for (int ky = 0; ky < 2; ++ky) {
          for (int kx = 0; kx < 2; ++kx) {
            dnn_i32 v = in[(ch * in_h + oy * 2 + ky) * in_w + ox * 2 + kx];
            if (v > max) {
              max = v;
            }
          }
        }
        out[(ch * out_h + oy) * out_w + ox] = max;
      }
    }
  }
}

void dnn_dense(const dnn_i32 *in, int in_n, const dnn_i32 *w, const dnn_i32 *b,
               int out_n, dnn_i32 *out) {
  for (int o = 0; o < out_n; ++o) {
    dnn_i32 acc = b[o];
    for (int i = 0; i < in_n; ++i) {
      acc += in[i] * w[o * in_n + i];
    }
    out[o] = acc;
  }
}

void dnn_channel_sum(const dnn_i32 *in, int c, int h, int in_w, dnn_i32 *out) {
  for (int ch = 0; ch < c; ++ch) {
    dnn_i32 acc = 0;
    for (int y = 0; y < h; ++y) {
      for (int x = 0; x < in_w; ++x) {
        acc += in[(ch * h + y) * in_w + x];
      }
    }
    out[ch] = acc;
  }
}

int dnn_argmax(const dnn_i32 *x, int n) {
  int best = 0;
  for (int i = 1; i < n; ++i) {
    if (x[i] > x[best]) {
      best = i;
    }
  }
  return best;
}

int dnn_check(const char *name, const dnn_i32 *got, const dnn_i32 *exp, int n) {
  for (int i = 0; i < n; ++i) {
    if (got[i] != exp[i]) {
      printf("%s FAILED at %d: expected %ld, got %ld\n", name, i, (long)exp[i],
             (long)got[i]);
      return 0;
    }
  }
  return 1;
}

void dnn_scale_relu(dnn_i32 *x, int n, int scale) {
  for (int i = 0; i < n; ++i) {
    dnn_i32 v = x[i] / scale;
    x[i] = v > 0 ? v : 0;
  }
}

void dnn_scale(dnn_i32 *x, int n, int scale) {
  for (int i = 0; i < n; ++i) {
    x[i] /= scale;
  }
}

int dnn_any_nonzero(const dnn_i32 *x, int n) {
  for (int i = 0; i < n; ++i) {
    if (x[i] != 0) {
      return 1;
    }
  }
  return 0;
}
