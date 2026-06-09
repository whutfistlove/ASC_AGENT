#ifndef LIBASCENDCXX_INCLUDE_ASCEND_STD___UTILITY_MOVE_H_
#define LIBASCENDCXX_INCLUDE_ASCEND_STD___UTILITY_MOVE_H_

#include "ascend/std/__config"
#include "ascend/std/__type_traits/remove_reference.h"

_ASCEND_STD_BEGIN

template <class _Tp>
_ASCEND_AICORE_FN constexpr remove_reference_t<_Tp>&& move(_Tp&& __t) noexcept
{
  return static_cast<remove_reference_t<_Tp>&&>(__t);
}

_ASCEND_STD_END

#endif  // LIBASCENDCXX_INCLUDE_ASCEND_STD___UTILITY_MOVE_H_
