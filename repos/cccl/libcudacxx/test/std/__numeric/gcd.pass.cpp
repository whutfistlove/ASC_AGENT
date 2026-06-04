//===----------------------------------------------------------------------===//
//
// Part of libcu++, the C++ Standard Library for your entire system,
// under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//

// Reference test for cuda::std::gcd (see __numeric/gcd.h).
//
// Semantics (ground truth for migration):
//   gcd(m, n) -> greatest common divisor of |m| and |n|; non-negative result.
//   gcd(x, 0) == gcd(0, x) == |x|; gcd(0, 0) == 0; sign of inputs does not matter.
// Binary, value-returning, integer op.

#include <cuda/std/__numeric/gcd.h>
#include <cassert>

int main(int, char**)
{
  assert(cuda::std::gcd(12, 18) == 6);
  assert(cuda::std::gcd(18, 12) == 6);
  assert(cuda::std::gcd(48, 36) == 12);
  assert(cuda::std::gcd(7, 13) == 1);    // coprime

  // Zero and identity behaviour.
  assert(cuda::std::gcd(0, 5) == 5);
  assert(cuda::std::gcd(5, 0) == 5);
  assert(cuda::std::gcd(0, 0) == 0);

  // Sign-insensitive.
  assert(cuda::std::gcd(-12, 18) == 6);
  assert(cuda::std::gcd(12, -18) == 6);
  assert(cuda::std::gcd(-12, -18) == 6);

  return 0;
}
