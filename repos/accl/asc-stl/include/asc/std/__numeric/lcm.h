#ifndef ASC_STL_INCLUDE_ASC_STD___NUMERIC_LCM_H_
#define ASC_STL_INCLUDE_ASC_STD___NUMERIC_LCM_H_

#include "asc/std/__config"

#if defined(__CCE__)
#define ASC_DEVICE_CODE
#endif

#include "asc/std/__numeric/gcd.h"

_ASC_STD_BEGIN

// Least common multiple of |__m| and |__n|. lcm(x, 0) == lcm(0, x) == 0.
// Computed as (|__m| / gcd(__m, __n)) * |__n| to avoid intermediate overflow.
template <typename _Tp>
_ASC_AICORE_FN constexpr _Tp lcm(_Tp __m, _Tp __n)
{
  if (__m == 0 || __n == 0)
  {
    return 0;
  }
  _Tp __a = __m < 0 ? -__m : __m;
  _Tp __b = __n < 0 ? -__n : __n;
  return (__a / asc::std::gcd(__a, __b)) * __b;
}

_ASC_STD_END

#endif // ASC_STL_INCLUDE_ASC_STD___NUMERIC_LCM_H_
