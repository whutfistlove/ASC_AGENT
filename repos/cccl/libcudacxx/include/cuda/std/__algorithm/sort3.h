//===----------------------------------------------------------------------===//
//
// Part of libcu++, the C++ Standard Library for your entire system,
// under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//

#ifndef _CUDA_STD__ALGORITHM_SORT3_H
#define _CUDA_STD__ALGORITHM_SORT3_H

#include <cuda/std/detail/__config>

#if defined(_CCCL_IMPLICIT_SYSTEM_HEADER_GCC)
#  pragma GCC system_header
#endif // no system header

_LIBCUDACXX_BEGIN_NAMESPACE_STD

// Synthetic migration-test operator: a fixed-size sorting network.
//
// sort3 takes three scalars by value and writes them back in ascending order
// through three output references:
//   lo <= mid <= hi   and   {lo, mid, hi} is a permutation of {a, b, c}.
//
// Unlike quad_fanout (pure arithmetic fan-out), sort3 carries data-dependent
// branching (three compare-exchanges) together with a 3-input / 3-output shape,
// so a migrated kernel_spec must use gm_inputs=3, gm_outputs=3 and a branchy,
// INDEPENDENT golden -- it cannot reuse the historical x/y -> z scaffold. The
// result is exact for integral types and order-preserving for floating point,
// so the migrator should pick dtype=int32_t for the integer slices.
template <class _Tp>
_CCCL_API constexpr void sort3(_Tp __a, _Tp __b, _Tp __c, _Tp& __lo, _Tp& __mid, _Tp& __hi)
{
  // Three compare-exchanges sort (a, b, c) into ascending order in place.
  if (__b < __a)
  {
    _Tp __t = __a;
    __a     = __b;
    __b     = __t;
  }
  if (__c < __a)
  {
    _Tp __t = __a;
    __a     = __c;
    __c     = __t;
  }
  if (__c < __b)
  {
    _Tp __t = __b;
    __b     = __c;
    __c     = __t;
  }
  __lo  = __a;
  __mid = __b;
  __hi  = __c;
}

_LIBCUDACXX_END_NAMESPACE_STD

#endif // _CUDA_STD__ALGORITHM_SORT3_H
