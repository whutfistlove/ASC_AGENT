#ifndef LIBASCENDCXX_INCLUDE_ASCEND_STD___ALGORITHM_COMP_H_
#define LIBASCENDCXX_INCLUDE_ASCEND_STD___ALGORITHM_COMP_H_

#include "ascend/std/__config"

_ASCEND_STD_BEGIN

struct __equal_to {
  template <class _T1, class _T2>
  _ASCEND_AICORE_FN constexpr bool operator()(const _T1& __lhs, const _T2& __rhs) const
  {
    return __lhs == __rhs;
  }
};

struct __less {
  template <class _T1, class _T2>
  _ASCEND_AICORE_FN constexpr bool operator()(const _T1& __lhs, const _T2& __rhs) const
  {
    return __lhs < __rhs;
  }
};

_ASCEND_STD_END

#endif  // LIBASCENDCXX_INCLUDE_ASCEND_STD___ALGORITHM_COMP_H_
