//===----------------------------------------------------------------------===//
//
// Part of libcu++, the C++ Standard Library for your entire system,
// under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//

// Reference test for cuda::std::saturate_sub (see __numeric/saturate_sub.h).
//
// Semantics (ground truth for migration):
//   saturate_sub(a, b) returns (a - b) when a > b, otherwise 0. Binary ->
//   single output, so a migrated kernel_spec should use gm_inputs=2,
//   gm_outputs=1 with an independent golden such as
//   (y_ref < x_ref) ? (x_ref - y_ref) : 0.

#include <cuda/std/__numeric/saturate_sub.h>
#include <cassert>

int main(int, char**)
{
  assert(cuda::std::saturate_sub(5, 2) == 3);
  assert(cuda::std::saturate_sub(2, 5) == 0);  // saturates at zero
  assert(cuda::std::saturate_sub(7, 7) == 0);
  assert(cuda::std::saturate_sub(10, 0) == 10);
  assert(cuda::std::saturate_sub(2.5, 1.0) == 1.5);
  assert(cuda::std::saturate_sub(1.0, 2.5) == 0.0);

  static_assert(cuda::std::saturate_sub(5, 2) == 3, "");

  return 0;
}
