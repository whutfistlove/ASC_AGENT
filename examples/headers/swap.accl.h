#ifndef ASC_STL_INCLUDE_ASC_STD___UTILITY_SWAP_H_
#define ASC_STL_INCLUDE_ASC_STD___UTILITY_SWAP_H_

#include <cstddef>
#include "asc/std/__config"
#include "asc/std/__utility/move.h"

_ASC_STD_BEGIN

template <typename _Tp>
_ASC_AICORE_FN constexpr void swap(_Tp& __a, _Tp& __b) noexcept
{
  _Tp __tmp(asc::std::move(__a));
  __a = asc::std::move(__b);
  __b = asc::std::move(__tmp);
}

template <typename _Tp, size_t _Np>
_ASC_AICORE_FN constexpr void swap(_Tp (&__a)[_Np], _Tp (&__b)[_Np]) noexcept
{
  for (size_t __i = 0; __i < _Np; ++__i)
  {
    asc::std::swap(__a[__i], __b[__i]);
  }
}

_ASC_STD_END

#endif  // ASC_STL_INCLUDE_ASC_STD___UTILITY_SWAP_H_
