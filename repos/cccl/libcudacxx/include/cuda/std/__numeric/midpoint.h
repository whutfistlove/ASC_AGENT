//===----------------------------------------------------------------------===//
//
// Part of libcu++, the C++ Standard Library for your entire system,
// under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//

#ifndef _CUDA_STD__NUMERIC_MIDPOINT_H
#define _CUDA_STD__NUMERIC_MIDPOINT_H

#include <cuda/std/detail/__config>

#if defined(_CCCL_IMPLICIT_SYSTEM_HEADER_GCC)
#  pragma GCC system_header
#endif // no system header

_LIBCUDACXX_BEGIN_NAMESPACE_STD

// Midpoint of __a and __b, computed as __a + (__b - __a) / 2 so it cannot
// overflow the range of the operands. For integers this rounds toward __a.
template <class _Tp>
_CCCL_API constexpr _Tp midpoint(_Tp __a, _Tp __b) noexcept
{
  return __a + (__b - __a) / 2;
}

_LIBCUDACXX_END_NAMESPACE_STD

#endif // _CUDA_STD__NUMERIC_MIDPOINT_H
