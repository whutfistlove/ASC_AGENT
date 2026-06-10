//===----------------------------------------------------------------------===//
//
// Part of libcu++, the C++ Standard Library for your entire system,
// under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//

// Reference test for cuda::std::sort3 (see __algorithm/sort3.h).
//
// Semantics (ground truth for migration):
//   sort3(a, b, c, lo, mid, hi) returns void and writes the three inputs back
//   in ascending order:
//     lo  = min(a, b, c)
//     hi  = max(a, b, c)
//     mid = the remaining value  (== a + b + c - lo - hi)
//   so that lo <= mid <= hi and {lo, mid, hi} is a permutation of {a, b, c}.
//
// This synthetic operator is a 3-input / 3-output, data-dependent (branchy)
// case. A migrated kernel_spec should use gm_inputs=3 and gm_outputs=3, fill
// h_in0..h_in2, out0_val..out2_val and expected0..expected2, and -- because the
// integer cases below demand exact ordering -- pick dtype=int32_t. The golden
// must be INDEPENDENT (e.g. ternary min/max plus mid = sum - lo - hi), never a
// second call into asc::std::sort3.

#include <cuda/std/__algorithm/sort3.h>
#include <cassert>

int main(int, char**)
{
  { // already sorted
    int lo = 0, mid = 0, hi = 0;
    cuda::std::sort3(1, 2, 3, lo, mid, hi);
    assert(lo == 1);
    assert(mid == 2);
    assert(hi == 3);
  }

  { // fully reversed
    int lo = 0, mid = 0, hi = 0;
    cuda::std::sort3(3, 2, 1, lo, mid, hi);
    assert(lo == 1);
    assert(mid == 2);
    assert(hi == 3);
  }

  { // duplicates are preserved
    int lo = 0, mid = 0, hi = 0;
    cuda::std::sort3(5, 1, 5, lo, mid, hi);
    assert(lo == 1);
    assert(mid == 5);
    assert(hi == 5);
  }

  { // negative values
    int lo = 0, mid = 0, hi = 0;
    cuda::std::sort3(-4, -9, -1, lo, mid, hi);
    assert(lo == -9);
    assert(mid == -4);
    assert(hi == -1);
  }

  { // floating point ordering
    float lo = 0.0f, mid = 0.0f, hi = 0.0f;
    cuda::std::sort3(2.5f, -1.0f, 0.5f, lo, mid, hi);
    assert(lo == -1.0f);
    assert(mid == 0.5f);
    assert(hi == 2.5f);
  }

  return 0;
}
