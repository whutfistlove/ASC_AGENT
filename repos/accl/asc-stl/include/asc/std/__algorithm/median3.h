#ifndef ASC_STL_INCLUDE_ASC_STD___ALGORITHM_MEDIAN3_H_
#define ASC_STL_INCLUDE_ASC_STD___ALGORITHM_MEDIAN3_H_

#include "asc/std/__config"

#if defined(__CCE__)
#define ASC_DEVICE_CODE
#endif

_ASC_STD_BEGIN

// median3(a, b, c) returns the middle of the three values by branchless
// comparison, with no in-tree dependencies.
template <typename _Tp>
_ASC_AICORE_FN constexpr const _Tp& median3(const _Tp& __a, const _Tp& __b, const _Tp& __c)
{
  return (__a < __b) ? ((__b < __c) ? __b : ((__a < __c) ? __c : __a))
                     : ((__a < __c) ? __a : ((__b < __c) ? __c : __b));
}

_ASC_STD_END

#endif // ASC_STL_INCLUDE_ASC_STD___ALGORITHM_MEDIAN3_H_
