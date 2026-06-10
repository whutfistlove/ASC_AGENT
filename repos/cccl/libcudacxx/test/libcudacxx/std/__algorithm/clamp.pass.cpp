//===----------------------------------------------------------------------===//
//
// Part of libcu++, the C++ Standard Library for your entire system,
// under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//

// Reference test for cuda::std::clamp (see __algorithm/clamp.h).
//
// Semantics (ground truth for migration):
//   clamp(v, lo, hi)        -> lo if v < lo; hi if hi < v; otherwise v.
//   clamp(v, lo, hi, comp)  -> same, using comp instead of operator<.
// This is a THREE-argument operator returning a const reference. A migrated
// test must feed all three operands (a value and two bounds), not two.

#include <cuda/std/__algorithm/clamp.h>
#include <cassert>

int main(int, char**)
{
  // Within range -> returns v unchanged.
  assert(cuda::std::clamp(5, 0, 10) == 5);

  // Below the low bound -> returns lo.
  assert(cuda::std::clamp(-3, 0, 10) == 0);

  // Above the high bound -> returns hi.
  assert(cuda::std::clamp(42, 0, 10) == 10);

  // Floating point, clamped to the upper bound.
  assert(cuda::std::clamp(2.5f, 1.0f, 2.0f) == 2.0f);

  // Boundaries are inclusive.
  assert(cuda::std::clamp(0, 0, 10) == 0);
  assert(cuda::std::clamp(10, 0, 10) == 10);

  // Custom comparator (plain operator<).
  {
    auto comp = [](int x, int y) { return x < y; };
    assert(cuda::std::clamp(42, 0, 10, comp) == 10);
  }

  return 0;
}
