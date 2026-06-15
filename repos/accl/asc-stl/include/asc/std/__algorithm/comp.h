#ifndef ASC_STL_INCLUDE_ASC_STD___ALGORITHM_COMP_H_
#define ASC_STL_INCLUDE_ASC_STD___ALGORITHM_COMP_H_

#include "asc/std/__config"

#if defined(__CCE__)
#define ASC_DEVICE_CODE
#endif

#include "asc/std/__type_traits/integral_constant.h"

_ASC_STD_BEGIN

struct __equal_to
{
  template <typename _T1, typename _T2>
  _ASC_AICORE_FN constexpr bool operator()(const _T1& __lhs, const _T2& __rhs) const
    noexcept(noexcept(__lhs == __rhs))
  {
    return __lhs == __rhs;
  }
};

struct __less
{
  template <typename _Tp, typename _Up>
  _ASC_AICORE_FN constexpr bool operator()(const _Tp& __lhs, const _Up& __rhs) const
    noexcept(noexcept(__lhs < __rhs))
  {
    return __lhs < __rhs;
  }
};

_ASC_STD_END

#endif  // ASC_STL_INCLUDE_ASC_STD___ALGORITHM_COMP_H_
