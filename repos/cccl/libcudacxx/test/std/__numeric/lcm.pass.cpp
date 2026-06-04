//===----------------------------------------------------------------------===//
//
// Part of libcu++, the C++ Standard Library for your entire system,
// under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//

// Reference test for cuda::std::lcm (see __numeric/lcm.h).
//
// Semantics (ground truth for migration):
//   lcm(m, n) -> least common multiple of |m| and |n|; non-negative result.
//   lcm(x, 0) == lcm(0, x) == 0; sign of inputs does not matter.
// Binary, value-returning, integer op (depends on gcd).

#include <cuda/std/__numeric/lcm.h>
#include <cassert>

int main(int, char**)
{
  assert(cuda::std::lcm(4, 6) == 12);
  assert(cuda::std::lcm(6, 4) == 12);
  assert(cuda::std::lcm(7, 13) == 91);   // coprime -> product
  assert(cuda::std::lcm(3, 9) == 9);     // multiple

  // Zero absorbs.
  assert(cuda::std::lcm(0, 5) == 0);
  assert(cuda::std::lcm(5, 0) == 0);
  assert(cuda::std::lcm(0, 0) == 0);

  // Sign-insensitive.
  assert(cuda::std::lcm(-4, 6) == 12);
  assert(cuda::std::lcm(4, -6) == 12);

  return 0;
}
