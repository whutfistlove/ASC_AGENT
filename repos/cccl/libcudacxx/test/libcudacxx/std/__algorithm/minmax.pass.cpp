//===----------------------------------------------------------------------===//
//
// Part of libcu++, the C++ Standard Library for your entire system,
// under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//

// Reference test for cuda::std::minmax (see __algorithm/minmax.h).
//
// Semantics (ground truth for migration):
//   minmax(a, b)       -> pair{min, max} under operator<; ties keep order {a, b}.
//   minmax(a, b, comp) -> same, using comp.
// MULTI-OUTPUT op: returns a pair. A migrated kernel test uses a single output
// buffer, so it checks one component at a time (e.g. .first); the host test can
// assert both components at once.

#include <cuda/std/__algorithm/minmax.h>
#include <cassert>

int main(int, char**)
{
  {
    auto pr = cuda::std::minmax(3, 8);
    assert(pr.first == 3 && pr.second == 8);
  }
  {
    auto pr = cuda::std::minmax(8, 3);
    assert(pr.first == 3 && pr.second == 8);
  }
  {
    auto pr = cuda::std::minmax(5, 5);   // equal -> {a, b}
    assert(pr.first == 5 && pr.second == 5);
  }
  {
    auto comp = [](int a, int b) { return a < b; };
    auto pr   = cuda::std::minmax(8, 3, comp);
    assert(pr.first == 3 && pr.second == 8);
  }
  return 0;
}
