//===----------------------------------------------------------------------===//
//
// Part of libcu++, the C++ Standard Library for your entire system,
// under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//

// Reference test for cuda::std::abs_diff (see __numeric/abs_diff.h).
//
// Semantics (ground truth for migration):
//   abs_diff(a, b) returns |a - b|. Binary -> single output, so a migrated
//   kernel_spec should use gm_inputs=2, gm_outputs=1 with an independent golden
//   such as (x_ref < y_ref) ? (y_ref - x_ref) : (x_ref - y_ref).

#include <cuda/std/__numeric/abs_diff.h>
#include <cassert>

int main(int, char**)
{
  assert(cuda::std::abs_diff(2, 5) == 3);
  assert(cuda::std::abs_diff(5, 2) == 3);
  assert(cuda::std::abs_diff(-4, 3) == 7);
  assert(cuda::std::abs_diff(7, 7) == 0);
  assert(cuda::std::abs_diff(2.5, 1.0) == 1.5);

  static_assert(cuda::std::abs_diff(5, 2) == 3, "");

  return 0;
}
