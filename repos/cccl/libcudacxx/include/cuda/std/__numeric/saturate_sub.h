//===----------------------------------------------------------------------===//
//
// Part of libcu++, the C++ Standard Library for your entire system,
// under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//

#ifndef _CUDA_STD__NUMERIC_SATURATE_SUB_H
#define _CUDA_STD__NUMERIC_SATURATE_SUB_H

#include <cuda/std/detail/__config>

#if defined(_CCCL_IMPLICIT_SYSTEM_HEADER_GCC)
#  pragma GCC system_header
#endif // no system header

_LIBCUDACXX_BEGIN_NAMESPACE_STD

// Synthetic migration-test operator (dependency-closure fixture: leaf level).
//
// saturate_sub(a, b) returns the non-negative (saturating) difference:
//   a - b if a > b, otherwise 0. No in-tree dependencies.
// Binary -> single output: a migrated kernel_spec should use gm_inputs=2,
// gm_outputs=1.
template <class _Tp>
_CCCL_API constexpr _Tp saturate_sub(const _Tp& __a, const _Tp& __b)
{
  return (__b < __a) ? static_cast<_Tp>(__a - __b) : static_cast<_Tp>(0);
}

_LIBCUDACXX_END_NAMESPACE_STD

#endif // _CUDA_STD__NUMERIC_SATURATE_SUB_H
