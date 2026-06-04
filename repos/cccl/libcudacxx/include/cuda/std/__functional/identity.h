//===----------------------------------------------------------------------===//
//
// Part of libcu++, the C++ Standard Library for your entire system,
// under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//

#ifndef _CUDA_STD__FUNCTIONAL_IDENTITY_H
#define _CUDA_STD__FUNCTIONAL_IDENTITY_H

#include <cuda/std/detail/__config>

#if defined(_CCCL_IMPLICIT_SYSTEM_HEADER_GCC)
#  pragma GCC system_header
#endif // no system header

_LIBCUDACXX_BEGIN_NAMESPACE_STD

struct identity
{
  template <class _Tp>
  _CCCL_API constexpr _Tp&& operator()(_Tp&& __t) const noexcept
  {
    return _CUDA_VSTD::forward<_Tp>(__t);
  }

  using is_transparent = void;
};

_LIBCUDACXX_END_NAMESPACE_STD

#endif // _CUDA_STD__FUNCTIONAL_IDENTITY_H
