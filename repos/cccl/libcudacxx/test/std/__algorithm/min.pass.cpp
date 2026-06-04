//===----------------------------------------------------------------------===//
//
// Part of libcu++, the C++ Standard Library for your entire system,
// under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//

// Reference test for cuda::std::min (see __algorithm/min.h).
//
// Semantics (ground truth for migration):
//   min(a, b)        -> the smaller of a, b under operator<; if equal, returns a.
//   min(a, b, comp)  -> the smaller under comp; if equal, returns a.
// The result is returned by const reference (no copy, no mutation of inputs).

#include <cuda/std/__algorithm/min.h>
#include <cassert>

int main(int, char**)
{
  // Basic ordering on integers and floats.
  assert(cuda::std::min(1, 2) == 1);
  assert(cuda::std::min(2, 1) == 1);
  assert(cuda::std::min(5.0f, 3.0f) == 3.0f);
  assert(cuda::std::min(-4, -9) == -9);

  // Equal values: the first argument is returned (by reference).
  {
    int a = 7;
    int b = 7;
    assert(&cuda::std::min(a, b) == &a);
  }

  // Custom comparator (plain operator< wrapped in a lambda).
  {
    auto comp = [](int x, int y) { return x < y; };
    assert(cuda::std::min(10, 20, comp) == 10);
    assert(cuda::std::min(20, 10, comp) == 10);
  }

  return 0;
}
