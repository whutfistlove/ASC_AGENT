//===----------------------------------------------------------------------===//
//
// Part of libcu++, the C++ Standard Library for your entire system,
// under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//

// Reference test for cuda::std::max (see __algorithm/max.h).
//
// Semantics (ground truth for migration):
//   max(a, b)        -> the greater of a, b under operator<; if equal, returns a.
//   max(a, b, comp)  -> the greater under comp; if equal, returns a.
// The result is returned by const reference (no copy, no mutation of inputs).

#include <cuda/std/__algorithm/max.h>
#include <cassert>

int main(int, char**)
{
  // Basic ordering on integers and floats.
  assert(cuda::std::max(1, 2) == 2);
  assert(cuda::std::max(2, 1) == 2);
  assert(cuda::std::max(5.0f, 3.0f) == 5.0f);
  assert(cuda::std::max(-4, -9) == -4);

  // Equal values: the first argument is returned (by reference).
  {
    int a = 7;
    int b = 7;
    assert(&cuda::std::max(a, b) == &a);
  }

  // Custom comparator (plain operator< wrapped in a lambda).
  {
    auto comp = [](int x, int y) { return x < y; };
    assert(cuda::std::max(10, 20, comp) == 20);
    assert(cuda::std::max(20, 10, comp) == 20);
  }

  return 0;
}
