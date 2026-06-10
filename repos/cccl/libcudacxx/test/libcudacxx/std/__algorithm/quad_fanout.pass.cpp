//===----------------------------------------------------------------------===//
//
// Part of libcu++, the C++ Standard Library for your entire system,
// under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//

// Reference test for cuda::std::quad_fanout (see __algorithm/quad_fanout.h).
//
// Semantics (ground truth for migration):
//   quad_fanout(a, b, c, d, out0, out1, out2, out3, out4) returns void and
//   writes five independent outputs:
//     out0 = a + b
//     out1 = b + c
//     out2 = c + d
//     out3 = a - d
//     out4 = a + b + c + d
//
// This synthetic operator is deliberately a 4-input / 5-output case. A migrated
// kernel_spec should use gm_inputs=4 and gm_outputs=5, filling h_in0..h_in3,
// out0_val..out4_val, and expected0..expected4.

#include <cuda/std/__algorithm/quad_fanout.h>
#include <cassert>

int main(int, char**)
{
  {
    int out0 = 0;
    int out1 = 0;
    int out2 = 0;
    int out3 = 0;
    int out4 = 0;

    cuda::std::quad_fanout(1, 2, 3, 4, out0, out1, out2, out3, out4);

    assert(out0 == 3);
    assert(out1 == 5);
    assert(out2 == 7);
    assert(out3 == -3);
    assert(out4 == 10);
  }

  {
    float out0 = 0.0f;
    float out1 = 0.0f;
    float out2 = 0.0f;
    float out3 = 0.0f;
    float out4 = 0.0f;

    cuda::std::quad_fanout(1.5f, -2.0f, 4.0f, 8.0f, out0, out1, out2, out3, out4);

    assert(out0 == -0.5f);
    assert(out1 == 2.0f);
    assert(out2 == 12.0f);
    assert(out3 == -6.5f);
    assert(out4 == 11.5f);
  }

  return 0;
}
