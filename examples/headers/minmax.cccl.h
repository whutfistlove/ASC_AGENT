//===----------------------------------------------------------------------===//
//
// Part of libcu++, the C++ Standard Library for your entire system,
// under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//

#ifndef _CUDA_STD__ALGORITHM_MINMAX_H
#define _CUDA_STD__ALGORITHM_MINMAX_H

#include <cuda/std/detail/__config>

#if defined(_CCCL_IMPLICIT_SYSTEM_HEADER_GCC)
#  pragma GCC system_header
#endif // no system header

#include <cuda/std/__functional/comparator.h>
#include <cuda/std/__utility/pair.h>

_LIBCUDACXX_BEGIN_NAMESPACE_STD

// Returns {min, max} as a pair of const references. If __a and __b are
// equivalent, the pair is {__a, __b} (i.e. ties keep the original order).
template <class _Tp, class _Compare>
_CCCL_API constexpr pair<const _Tp&, const _Tp&> minmax(const _Tp& __a, const _Tp& __b, _Compare __comp)
{
  return __comp(__b, __a) ? pair<const _Tp&, const _Tp&>(__b, __a) : pair<const _Tp&, const _Tp&>(__a, __b);
}

template <class _Tp>
_CCCL_API constexpr pair<const _Tp&, const _Tp&> minmax(const _Tp& __a, const _Tp& __b)
{
  return (__b < __a) ? pair<const _Tp&, const _Tp&>(__b, __a) : pair<const _Tp&, const _Tp&>(__a, __b);
}

_LIBCUDACXX_END_NAMESPACE_STD

#endif // _CUDA_STD__ALGORITHM_MINMAX_H
