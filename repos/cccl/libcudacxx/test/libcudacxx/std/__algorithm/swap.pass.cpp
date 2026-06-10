//===----------------------------------------------------------------------===//
//
// Part of libcu++, the C++ Standard Library for your entire system,
// under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//

// Reference test for cuda::std::swap (see __algorithm/swap.h).
//
// Semantics (ground truth for migration):
//   swap(a, b)            -> exchanges the values of a and b IN PLACE. Returns void.
//   swap(a[N], b[N])      -> exchanges two arrays element by element. Returns void.
// swap takes lvalue references and must NOT be turned into a value-returning
// function: the whole point is the in-place exchange of the two operands.

#include <cuda/std/__algorithm/swap.h>
#include <cassert>

int main(int, char**)
{
  // Scalar exchange.
  {
    int a = 1;
    int b = 2;
    cuda::std::swap(a, b);
    assert(a == 2);
    assert(b == 1);
  }

  // Floating point exchange.
  {
    float x = 3.5f;
    float y = -1.0f;
    cuda::std::swap(x, y);
    assert(x == -1.0f);
    assert(y == 3.5f);
  }

  // Array overload: every element is exchanged.
  {
    int u[3] = {1, 2, 3};
    int v[3] = {4, 5, 6};
    cuda::std::swap(u, v);
    assert(u[0] == 4 && u[1] == 5 && u[2] == 6);
    assert(v[0] == 1 && v[1] == 2 && v[2] == 3);
  }

  return 0;
}
