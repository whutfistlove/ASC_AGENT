#ifndef ASC_STL_INCLUDE_ASC_STD___NUMERIC_SATURATE_SUB_H_
#define ASC_STL_INCLUDE_ASC_STD___NUMERIC_SATURATE_SUB_H_

#include "asc/std/__config"

#if defined(__CCE__)
#define ASC_DEVICE_CODE
#endif

_ASC_STD_BEGIN

// Synthetic migration-test operator (dependency-closure fixture: leaf level).
//
// saturate_sub(a, b) returns the non-negative (saturating) difference:
//   a - b if a > b, otherwise 0. No in-tree dependencies.
// Binary -> single output: a migrated kernel_spec should use gm_inputs=2,
// gm_outputs=1.
template <typename _Tp>
_ASC_AICORE_FN constexpr _Tp saturate_sub(const _Tp& __a, const _Tp& __b)
{
  return (__b < __a) ? static_cast<_Tp>(__a - __b) : static_cast<_Tp>(0);
}

_ASC_STD_END

#endif // ASC_STL_INCLUDE_ASC_STD___NUMERIC_SATURATE_SUB_H_
