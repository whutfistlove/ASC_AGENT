//===----------------------------------------------------------------------===//
//
// Part of libcu++, the C++ Standard Library for your entire system,
// under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//

#ifndef _CUDA_STD__NUMERIC_LCM_H
#define _CUDA_STD__NUMERIC_LCM_H

#include <cuda/std/detail/__config>

#if defined(_CCCL_IMPLICIT_SYSTEM_HEADER_GCC)
#  pragma GCC system_header
#endif // no system header

#include <cuda/std/__numeric/gcd.h>

_LIBCUDACXX_BEGIN_NAMESPACE_STD

// Least common multiple of |__m| and |__n|. lcm(x, 0) == lcm(0, x) == 0.
// Computed as (|__m| / gcd(__m, __n)) * |__n| to avoid intermediate overflow.
template <class _Tp>
_CCCL_API constexpr _Tp lcm(_Tp __m, _Tp __n)
{
  if (__m == 0 || __n == 0)
  {
    return 0;
  }
  _Tp __a = __m < 0 ? -__m : __m;
  _Tp __b = __n < 0 ? -__n : __n;
  return (__a / _CUDA_VSTD::gcd(__a, __b)) * __b;
}

_LIBCUDACXX_END_NAMESPACE_STD

#endif // _CUDA_STD__NUMERIC_LCM_H
