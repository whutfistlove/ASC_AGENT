#ifndef LIBASCENDCXX_INCLUDE_ASCEND_STD___NUMERIC_ABS_DIFF_H_
#define LIBASCENDCXX_INCLUDE_ASCEND_STD___NUMERIC_ABS_DIFF_H_

#include "ascend/std/__config"

#if defined(__CCE__)
#define ASCEND_DEVICE_CODE
#endif

_ASCEND_STD_BEGIN

// Synthetic migration-test operator (dependency-closure fixture: leaf level).
//
// abs_diff(a, b) returns the absolute difference |a - b| as a value of type _Tp.
// It has no in-tree dependencies, so it is the leaf of the spread3 closure:
//   spread3 -> range_width -> abs_diff
// Binary -> single-output: a migrated kernel_spec should use gm_inputs=2,
// gm_outputs=1.
template <typename _Tp>
_ASCEND_AICORE_FN constexpr _Tp abs_diff(const _Tp& __a, const _Tp& __b)
{
  return (__a < __b) ? static_cast<_Tp>(__b - __a) : static_cast<_Tp>(__a - __b);
}

_ASCEND_STD_END

#endif  // LIBASCENDCXX_INCLUDE_ASCEND_STD___NUMERIC_ABS_DIFF_H_
