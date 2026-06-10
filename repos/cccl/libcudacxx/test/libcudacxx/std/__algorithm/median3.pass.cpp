//===----------------------------------------------------------------------===//
//
// Part of libcu++, the C++ Standard Library for your entire system,
// under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//

// Reference test for cuda::std::median3 (see __algorithm/median3.h).
//
// Semantics (ground truth for migration):
//   median3(a, b, c) returns the middle value of the three. This is a
//   THREE-argument operator returning a const reference. A migrated kernel_spec
//   should use gm_inputs=3, gm_outputs=1 with an independent golden such as the
//   sort-and-pick-middle of (x_ref, y_ref, w_ref).

#include <cuda/std/__algorithm/median3.h>
#include <cassert>

int main(int, char**)
{
  // Already sorted / reverse / middle-first orderings all pick the middle.
  assert(cuda::std::median3(1, 2, 3) == 2);
  assert(cuda::std::median3(3, 2, 1) == 2);
  assert(cuda::std::median3(2, 3, 1) == 2);
  assert(cuda::std::median3(3, 1, 2) == 2);

  // Duplicates are handled (the repeated value is the median).
  assert(cuda::std::median3(5, 5, 1) == 5);
  assert(cuda::std::median3(1, 7, 7) == 7);

  // Negative and floating point.
  assert(cuda::std::median3(-3, 0, 3) == 0);
  assert(cuda::std::median3(2.5f, 1.0f, 2.0f) == 2.0f);

  static_assert(cuda::std::median3(3, 1, 2) == 2, "");

  return 0;
}
