//===----------------------------------------------------------------------===//
//
// Part of libcu++, the C++ Standard Library for your entire system,
// under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//

// Reference test for cuda::std::midpoint (see __numeric/midpoint.h).
//
// Semantics (ground truth for migration):
//   midpoint(a, b) -> a + (b - a) / 2, computed without overflow.
//   For integers the result rounds toward a (the first argument).
// Binary, value-returning op.

#include <cuda/std/__numeric/midpoint.h>
#include <cassert>

int main(int, char**)
{
  assert(cuda::std::midpoint(2, 8) == 5);
  assert(cuda::std::midpoint(0, 10) == 5);
  assert(cuda::std::midpoint(7, 7) == 7);
  assert(cuda::std::midpoint(-10, 10) == 0);

  // Odd span rounds toward the FIRST argument.
  assert(cuda::std::midpoint(3, 4) == 3);
  assert(cuda::std::midpoint(4, 3) == 4);

  return 0;
}
