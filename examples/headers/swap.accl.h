#ifndef LIBASCENDCXX_INCLUDE_ASCEND_STD___ALGORITHM_SWAP_H_
#define LIBASCENDCXX_INCLUDE_ASCEND_STD___ALGORITHM_SWAP_H_

#include <cstddef>
#include "ascend/std/__config"

#if defined(__CCE__)
#define ASCEND_DEVICE_CODE
#endif

_ASCEND_STD_BEGIN

template <typename _Tp>
_ASCEND_AICORE_FN constexpr void swap(_Tp& __a, _Tp& __b) noexcept
{
  _Tp __tmp(static_cast<_Tp&&>(__a));
  __a = static_cast<_Tp&&>(__b);
  __b = static_cast<_Tp&&>(__tmp);
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

#endif  // LIBASCENDCXX_INCLUDE_ASCEND_STD___ALGORITHM_SWAP_H_
