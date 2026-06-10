#ifndef ASC_STL_INCLUDE_ASC_STD___NUMERIC_RANGE_WIDTH_H_
#define ASC_STL_INCLUDE_ASC_STD___NUMERIC_RANGE_WIDTH_H_

#include "asc/std/__config"
#include "asc/std/__numeric/abs_diff.h"
#include "asc/std/__algorithm/max.h"

#if defined(__CCE__)
#define ASC_DEVICE_CODE
#endif

_ASC_STD_BEGIN

// Synthetic migration-test operator (dependency-closure fixture: middle level).
//
// range_width(a, b, c) returns the largest pairwise absolute difference among
// the three inputs, which equals max(a, b, c) - min(a, b, c). It depends on:
//   - __numeric/abs_diff.h  (in-tree, new)      for the pairwise differences
//   - __algorithm/max.h     (in-tree, existing) to combine them
// so migrating it requires that closure to be migrated first. Three inputs ->
// single output: a migrated kernel_spec should use gm_inputs=3, gm_outputs=1.
template <typename _Tp>
_ASC_AICORE_FN constexpr _Tp range_width(const _Tp& __a, const _Tp& __b, const _Tp& __c) {
  return max(abs_diff(__a, __b), max(abs_diff(__b, __c), abs_diff(__a, __c)));
}

_ASC_STD_END

#endif  // ASC_STL_INCLUDE_ASC_STD___NUMERIC_RANGE_WIDTH_H_
