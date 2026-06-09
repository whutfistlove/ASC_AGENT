#ifndef LIBASCENDCXX_INCLUDE_ASCEND_STD___UTILITY_PAIR_H_
#define LIBASCENDCXX_INCLUDE_ASCEND_STD___UTILITY_PAIR_H_

#include "ascend/std/__config"
#include "ascend/std/__utility/forward.h"
#include "ascend/std/__utility/move.h"

_ASCEND_STD_BEGIN

template <class _T1, class _T2>
struct pair {
  using first_type = _T1;
  using second_type = _T2;

  _T1 first;
  _T2 second;

  _ASCEND_AICORE_FN constexpr pair() : first(), second() {}

  _ASCEND_AICORE_FN constexpr pair(const _T1& __first, const _T2& __second)
      : first(__first), second(__second)
  {}

  template <class _U1, class _U2>
  _ASCEND_AICORE_FN constexpr pair(_U1&& __first, _U2&& __second)
      : first(_ASCEND_STD::forward<_U1>(__first)), second(_ASCEND_STD::forward<_U2>(__second))
  {}

  template <class _U1, class _U2>
  _ASCEND_AICORE_FN constexpr pair(const pair<_U1, _U2>& __other)
      : first(__other.first), second(__other.second)
  {}

  template <class _U1, class _U2>
  _ASCEND_AICORE_FN constexpr pair(pair<_U1, _U2>&& __other)
      : first(_ASCEND_STD::forward<_U1>(__other.first)), second(_ASCEND_STD::forward<_U2>(__other.second))
  {}
};

template <class _T1, class _T2>
_ASCEND_AICORE_FN constexpr pair<_T1, _T2> make_pair(_T1 __first, _T2 __second)
{
  return pair<_T1, _T2>(_ASCEND_STD::move(__first), _ASCEND_STD::move(__second));
}

_ASCEND_STD_END

#endif  // LIBASCENDCXX_INCLUDE_ASCEND_STD___UTILITY_PAIR_H_
