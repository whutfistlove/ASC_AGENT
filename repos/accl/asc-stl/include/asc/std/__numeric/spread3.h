#ifndef ASC_STL_INCLUDE_ASC_STD___NUMERIC_SPREAD3_H_
#define ASC_STL_INCLUDE_ASC_STD___NUMERIC_SPREAD3_H_

#include "asc/std/__config"
#include "asc/std/__numeric/range_width.h"
#include "asc/std/__algorithm/min.h"

#if defined(__CCE__)
#define ASC_DEVICE_CODE
#endif

_ASC_STD_BEGIN

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
template <typename _Tp>
_ASC_AICORE_FN constexpr void spread3(
  const _Tp& __a, const _Tp& __b, const _Tp& __c, _Tp& __lo, _Tp& __width) {
  __lo    = min(__a, min(__b, __c));
  __width = range_width(__a, __b, __c);
}

_ASC_STD_END

#endif  // ASC_STL_INCLUDE_ASC_STD___NUMERIC_SPREAD3_H_
