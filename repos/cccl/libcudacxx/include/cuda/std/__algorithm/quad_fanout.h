//===----------------------------------------------------------------------===//
//
// Part of libcu++, the C++ Standard Library for your entire system,
// under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//

#ifndef _CUDA_STD__ALGORITHM_QUAD_FANOUT_H
#define _CUDA_STD__ALGORITHM_QUAD_FANOUT_H

#include <cuda/std/detail/__config>

#if defined(_CCCL_IMPLICIT_SYSTEM_HEADER_GCC)
#  pragma GCC system_header
#endif // no system header

_LIBCUDACXX_BEGIN_NAMESPACE_STD

// Synthetic migration test operator:
//   four scalar inputs, five output references, void return.
//
// This is intentionally wider than the common unary/binary std algorithms so the
// ACCL test migrator must generate a kernel_spec with gm_inputs=4 and
// gm_outputs=5 instead of falling back to the historical x/y -> z scaffold.
template <class _Tp>
_CCCL_API constexpr void quad_fanout(
  const _Tp& __a,
  const _Tp& __b,
  const _Tp& __c,
  const _Tp& __d,
  _Tp& __out0,
  _Tp& __out1,
  _Tp& __out2,
  _Tp& __out3,
  _Tp& __out4)
{
  __out0 = __a + __b;
  __out1 = __b + __c;
  __out2 = __c + __d;
  __out3 = __a - __d;
  __out4 = __a + __b + __c + __d;
}

_LIBCUDACXX_END_NAMESPACE_STD

#endif // _CUDA_STD__ALGORITHM_QUAD_FANOUT_H
