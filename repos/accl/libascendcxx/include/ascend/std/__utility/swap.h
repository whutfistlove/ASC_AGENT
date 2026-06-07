#ifndef LIBASCENDCXX_INCLUDE_ASCEND_STD___UTILITY_SWAP_H_
#define LIBASCENDCXX_INCLUDE_ASCEND_STD___UTILITY_SWAP_H_

#include <cstddef>
#include "ascend/std/__config"
#include "ascend/std/__utility/move.h"

_ASCEND_STD_BEGIN

template <typename _Tp>
_ASCEND_AICORE_FN constexpr void swap(_Tp& __a, _Tp& __b) noexcept
{
  _Tp __tmp(ascend::std::move(__a));
  __a = ascend::std::move(__b);
  __b = ascend::std::move(__tmp);
}

template <typename _Tp, size_t _Np>
_ASCEND_AICORE_FN constexpr void swap(_Tp (&__a)[_Np], _Tp (&__b)[_Np]) noexcept
{
  for (size_t __i = 0; __i < _Np; ++__i)
  {
    ascend::std::swap(__a[__i], __b[__i]);
  }
}

_ASCEND_STD_END

#endif  // LIBASCENDCXX_INCLUDE_ASCEND_STD___UTILITY_SWAP_H_
