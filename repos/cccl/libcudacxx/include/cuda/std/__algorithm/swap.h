//===----------------------------------------------------------------------===//
//
// Part of libcu++, the C++ Standard Library for your entire system,
// under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//

#ifndef _CUDA_STD__ALGORITHM_SWAP_H
#define _CUDA_STD__ALGORITHM_SWAP_H

#include <cuda/std/detail/__config>

#if defined(_CCCL_IMPLICIT_SYSTEM_HEADER_GCC)
#  pragma GCC system_header
#endif // no system header

_LIBCUDACXX_BEGIN_NAMESPACE_STD

template <class _Tp>
_CCCL_API constexpr void swap(_Tp& __a, _Tp& __b) noexcept
{
  _Tp __tmp(_CUDA_VSTD::move(__a));
  __a = _CUDA_VSTD::move(__b);
  __b = _CUDA_VSTD::move(__tmp);
}

template <class _Tp, size_t _Np>
_CCCL_API constexpr void swap(_Tp (&__a)[_Np], _Tp (&__b)[_Np]) noexcept
{
  for (size_t __i = 0; __i < _Np; ++__i)
  {
    _CUDA_VSTD::swap(__a[__i], __b[__i]);
  }
}

_LIBCUDACXX_END_NAMESPACE_STD

#endif // _CUDA_STD__ALGORITHM_SWAP_H
