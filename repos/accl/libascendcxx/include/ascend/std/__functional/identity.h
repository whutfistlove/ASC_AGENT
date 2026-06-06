#ifndef LIBASCENDCXX_INCLUDE_ASCEND_STD___FUNCTIONAL_IDENTITY_H_
#define LIBASCENDCXX_INCLUDE_ASCEND_STD___FUNCTIONAL_IDENTITY_H_

#include "ascend/std/__config"
#include "ascend/std/__utility/forward.h"

_ASCEND_STD_BEGIN

template <class _Tp>
inline constexpr bool __is_identity_v = false;

struct identity {
  template <class _Tp>
  _ASCEND_AICORE_FN constexpr _Tp&& operator()(_Tp&& __value) const noexcept
  {
    return _ASCEND_STD::forward<_Tp>(__value);
  }

  using is_transparent = void;
};

template <>
inline constexpr bool __is_identity_v<identity> = true;

_ASCEND_STD_END

#endif  // LIBASCENDCXX_INCLUDE_ASCEND_STD___FUNCTIONAL_IDENTITY_H_
