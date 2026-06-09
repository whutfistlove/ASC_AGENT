//===----------------------------------------------------------------------===//
//
// Part of libcu++, the C++ Standard Library for your entire system,
// under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//

// Reference test for cuda::std::spread3 (see __numeric/spread3.h).
//
// Semantics (ground truth for migration):
//   spread3(a, b, c, lo, width) is void and writes:
//     lo    = min(a, b, c)
//     width = max(a, b, c) - min(a, b, c)
//   Three inputs / two outputs, so a migrated kernel_spec should use
//   gm_inputs=3, gm_outputs=2, assigning out0_val = lo and out1_val = width,
//   with an independent golden for expected0 (min) and expected1 (max - min).
//
// This is the entry header of the dependency closure
//   abs_diff, max, min -> range_width -> spread3
// used to exercise dependency-closure migration end to end.

#include <cuda/std/__numeric/spread3.h>
#include <cassert>

int main(int, char**)
{
  {
    int lo = 0, width = 0;
    cuda::std::spread3(3, 1, 2, lo, width);
    assert(lo == 1);
    assert(width == 2);
  }
  {
    int lo = 0, width = 0;
    cuda::std::spread3(-4, 9, 1, lo, width);
    assert(lo == -4);
    assert(width == 13);
  }
  {
    int lo = 0, width = 0;
    cuda::std::spread3(7, 7, 7, lo, width);
    assert(lo == 7);
    assert(width == 0);
  }

  return 0;
}
