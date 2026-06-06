#ifndef LIBASCENDCXX_INCLUDE_ASCEND_STD___UTILITY_FORWARD_H_
#define LIBASCENDCXX_INCLUDE_ASCEND_STD___UTILITY_FORWARD_H_

#include "ascend/std/__config"
#include "ascend/std/__type_traits/is_reference.h"
#include "ascend/std/__type_traits/remove_reference.h"

_ASCEND_STD_BEGIN

template <class _Tp>
_ASCEND_AICORE_FN constexpr _Tp&& forward(remove_reference_t<_Tp>& __t) noexcept
{
  return static_cast<_Tp&&>(__t);
}

template <class _Tp>
_ASCEND_AICORE_FN constexpr _Tp&& forward(remove_reference_t<_Tp>&& __t) noexcept
{
  static_assert(!is_lvalue_reference_v<_Tp>, "cannot forward an rvalue as an lvalue");
  return static_cast<_Tp&&>(__t);
}

_ASCEND_STD_END

#endif  // LIBASCENDCXX_INCLUDE_ASCEND_STD___UTILITY_FORWARD_H_
