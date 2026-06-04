//===----------------------------------------------------------------------===//
//
// Part of libcu++, the C++ Standard Library for your entire system,
// under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//

#ifndef _CUDA_STD__NUMERIC_GCD_H
#define _CUDA_STD__NUMERIC_GCD_H

#include <cuda/std/detail/__config>

#if defined(_CCCL_IMPLICIT_SYSTEM_HEADER_GCC)
#  pragma GCC system_header
#endif // no system header

_LIBCUDACXX_BEGIN_NAMESPACE_STD

// Greatest common divisor of |__m| and |__n| (Euclid's algorithm).
// gcd(0, 0) == 0; the result is non-negative and sign-insensitive in the inputs.
template <class _Tp>
_CCCL_API constexpr _Tp gcd(_Tp __m, _Tp __n)
{
  __m = __m < 0 ? -__m : __m;
  __n = __n < 0 ? -__n : __n;
  while (__n != 0)
  {
    _Tp __t = __m % __n;
    __m     = __n;
    __n     = __t;
  }
  return __m;
}

_LIBCUDACXX_END_NAMESPACE_STD

#endif // _CUDA_STD__NUMERIC_GCD_H
