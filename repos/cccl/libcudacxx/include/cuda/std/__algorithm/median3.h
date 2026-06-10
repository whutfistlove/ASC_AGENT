//===----------------------------------------------------------------------===//
//
// Part of libcu++, the C++ Standard Library for your entire system,
// under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//

#ifndef _CUDA_STD__ALGORITHM_MEDIAN3_H
#define _CUDA_STD__ALGORITHM_MEDIAN3_H

#include <cuda/std/detail/__config>

#if defined(_CCCL_IMPLICIT_SYSTEM_HEADER_GCC)
#  pragma GCC system_header
#endif // no system header

_LIBCUDACXX_BEGIN_NAMESPACE_STD

// Synthetic migration-test operator (dependency-closure fixture: leaf level).
//
// median3(a, b, c) returns the middle of the three values by branchless
// comparison, with no in-tree dependencies.
// Ternary -> single output: a migrated kernel_spec should use gm_inputs=3,
// gm_outputs=1 with an independent golden.
template <class _Tp>
_CCCL_API constexpr const _Tp& median3(const _Tp& __a, const _Tp& __b, const _Tp& __c)
{
  return (__a < __b) ? ((__b < __c) ? __b : ((__a < __c) ? __c : __a))
                     : ((__a < __c) ? __a : ((__b < __c) ? __c : __b));
}

_LIBCUDACXX_END_NAMESPACE_STD

#endif // _CUDA_STD__ALGORITHM_MEDIAN3_H
