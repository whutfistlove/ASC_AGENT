#ifndef ASC_STL_INCLUDE_ASC_STD___NUMERIC_GCD_H_
#define ASC_STL_INCLUDE_ASC_STD___NUMERIC_GCD_H_

#include "asc/std/__config"

#if defined(__CCE__)
#define ASC_DEVICE_CODE
#endif

_ASC_STD_BEGIN

// Greatest common divisor of |__m| and |__n| (Euclid's algorithm).
// gcd(0, 0) == 0; the result is non-negative and sign-insensitive in the inputs.
template <typename _Tp>
_ASC_AICORE_FN constexpr _Tp gcd(_Tp __m, _Tp __n)
{
  __m = __m < 0 ? -__m : __m;
  __n = __n < 0 ? -__n : __n;
  while (__n != 0)
  {
    _Tp __t = __m % __n;
    __m     = __n;
    __n     = __t;
  }
  return __m;
}

_ASC_STD_END

#endif // ASC_STL_INCLUDE_ASC_STD___NUMERIC_GCD_H_
