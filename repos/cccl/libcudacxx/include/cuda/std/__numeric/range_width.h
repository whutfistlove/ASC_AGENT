//===----------------------------------------------------------------------===//
//
// Part of libcu++, the C++ Standard Library for your entire system,
// under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//

#ifndef _CUDA_STD__NUMERIC_RANGE_WIDTH_H
#define _CUDA_STD__NUMERIC_RANGE_WIDTH_H

#include <cuda/std/detail/__config>
#include <cuda/std/__numeric/abs_diff.h>
#include <cuda/std/__algorithm/max.h>

#if defined(_CCCL_IMPLICIT_SYSTEM_HEADER_GCC)
#  pragma GCC system_header
#endif // no system header

_LIBCUDACXX_BEGIN_NAMESPACE_STD

// Synthetic migration-test operator (dependency-closure fixture: middle level).
//
// range_width(a, b, c) returns the largest pairwise absolute difference among
// the three inputs, which equals max(a, b, c) - min(a, b, c). It depends on:
//   - __numeric/abs_diff.h  (in-tree, new)      for the pairwise differences
//   - __algorithm/max.h     (in-tree, existing) to combine them
// so migrating it requires that closure to be migrated first. Three inputs ->
// single output: a migrated kernel_spec should use gm_inputs=3, gm_outputs=1.
template <class _Tp>
_CCCL_API constexpr _Tp range_width(const _Tp& __a, const _Tp& __b, const _Tp& __c)
{
  return max(abs_diff(__a, __b), max(abs_diff(__b, __c), abs_diff(__a, __c)));
}

_LIBCUDACXX_END_NAMESPACE_STD

#endif // _CUDA_STD__NUMERIC_RANGE_WIDTH_H
