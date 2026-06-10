//===----------------------------------------------------------------------===//
//
// Part of libcu++, the C++ Standard Library for your entire system,
// under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//

// Reference test for cuda::std::range_width (see __numeric/range_width.h).
//
// Semantics (ground truth for migration):
//   range_width(a, b, c) == max(a, b, c) - min(a, b, c), the largest pairwise
//   absolute difference among the three inputs. Three inputs -> single output,
//   so a migrated kernel_spec should use gm_inputs=3, gm_outputs=1 with an
//   independent golden that recomputes max-min without calling asc::std::*.

#include <cuda/std/__numeric/range_width.h>
#include <cassert>

int main(int, char**)
{
  assert(cuda::std::range_width(1, 2, 3) == 2);
  assert(cuda::std::range_width(3, 1, 2) == 2);
  assert(cuda::std::range_width(5, 5, 5) == 0);
  assert(cuda::std::range_width(-4, 9, 1) == 13);
  assert(cuda::std::range_width(2, 2, 8) == 6);

  static_assert(cuda::std::range_width(1, 2, 3) == 2, "");

  return 0;
}
