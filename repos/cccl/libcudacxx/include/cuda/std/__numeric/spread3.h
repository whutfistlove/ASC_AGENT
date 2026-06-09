//===----------------------------------------------------------------------===//
//
// Part of libcu++, the C++ Standard Library for your entire system,
// under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
//
//===----------------------------------------------------------------------===//

#ifndef _CUDA_STD__NUMERIC_SPREAD3_H
#define _CUDA_STD__NUMERIC_SPREAD3_H

#include <cuda/std/detail/__config>
#include <cuda/std/__numeric/range_width.h>
#include <cuda/std/__algorithm/min.h>

#if defined(_CCCL_IMPLICIT_SYSTEM_HEADER_GCC)
#  pragma GCC system_header
#endif // no system header

_LIBCUDACXX_BEGIN_NAMESPACE_STD

// Synthetic migration-test operator (dependency-closure fixture: entry level).
//
// spread3(a, b, c, lo, width) returns void and writes two outputs:
//   lo    = the minimum of (a, b, c)
//   width = max(a, b, c) - min(a, b, c)   (the range width)
//
// Transitive dependency closure (leaf-first):
//   abs_diff , max , min  ->  range_width  ->  spread3
// spread3 depends on range_width (-> abs_diff, max) and min. This is the entry
// header used to exercise dependency-closure migration end to end: migrating it
// must first migrate range_width and abs_diff and reuse the already-migrated
// min/max. Three inputs / two outputs: gm_inputs=3, gm_outputs=2.
template <class _Tp>
_CCCL_API constexpr void spread3(
  const _Tp& __a, const _Tp& __b, const _Tp& __c, _Tp& __lo, _Tp& __width)
{
  __lo    = min(__a, min(__b, __c));
  __width = range_width(__a, __b, __c);
}

_LIBCUDACXX_END_NAMESPACE_STD

#endif // _CUDA_STD__NUMERIC_SPREAD3_H
