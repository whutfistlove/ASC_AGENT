#ifndef LIBASCENDCXX_INCLUDE_ASCEND_STD___FUNCTIONAL_OPERATIONS_H_
#define LIBASCENDCXX_INCLUDE_ASCEND_STD___FUNCTIONAL_OPERATIONS_H_

#include "ascend/std/__config"
#include "ascend/std/__utility/forward.h"

_ASCEND_STD_BEGIN

template <class _Tp = void>
struct plus {
  _ASCEND_AICORE_FN constexpr _Tp operator()(const _Tp& __lhs, const _Tp& __rhs) const
  {
    return __lhs + __rhs;
  }
};

template <>
struct plus<void> {
  template <class _T1, class _T2>
  _ASCEND_AICORE_FN constexpr auto operator()(_T1&& __lhs, _T2&& __rhs) const
      -> decltype(_ASCEND_STD::forward<_T1>(__lhs) + _ASCEND_STD::forward<_T2>(__rhs))
  {
    return _ASCEND_STD::forward<_T1>(__lhs) + _ASCEND_STD::forward<_T2>(__rhs);
  }

  using is_transparent = void;
};

template <class _Tp = void>
struct minus {
  _ASCEND_AICORE_FN constexpr _Tp operator()(const _Tp& __lhs, const _Tp& __rhs) const
  {
    return __lhs - __rhs;
  }
};

template <>
struct minus<void> {
  template <class _T1, class _T2>
  _ASCEND_AICORE_FN constexpr auto operator()(_T1&& __lhs, _T2&& __rhs) const
      -> decltype(_ASCEND_STD::forward<_T1>(__lhs) - _ASCEND_STD::forward<_T2>(__rhs))
  {
    return _ASCEND_STD::forward<_T1>(__lhs) - _ASCEND_STD::forward<_T2>(__rhs);
  }

  using is_transparent = void;
};

template <class _Tp = void>
struct multiplies {
  _ASCEND_AICORE_FN constexpr _Tp operator()(const _Tp& __lhs, const _Tp& __rhs) const
  {
    return __lhs * __rhs;
  }
};

template <>
struct multiplies<void> {
  template <class _T1, class _T2>
  _ASCEND_AICORE_FN constexpr auto operator()(_T1&& __lhs, _T2&& __rhs) const
      -> decltype(_ASCEND_STD::forward<_T1>(__lhs) * _ASCEND_STD::forward<_T2>(__rhs))
  {
    return _ASCEND_STD::forward<_T1>(__lhs) * _ASCEND_STD::forward<_T2>(__rhs);
  }

  using is_transparent = void;
};

template <class _Tp = void>
struct divides {
  _ASCEND_AICORE_FN constexpr _Tp operator()(const _Tp& __lhs, const _Tp& __rhs) const
  {
    return __lhs / __rhs;
  }
};

template <>
struct divides<void> {
  template <class _T1, class _T2>
  _ASCEND_AICORE_FN constexpr auto operator()(_T1&& __lhs, _T2&& __rhs) const
      -> decltype(_ASCEND_STD::forward<_T1>(__lhs) / _ASCEND_STD::forward<_T2>(__rhs))
  {
    return _ASCEND_STD::forward<_T1>(__lhs) / _ASCEND_STD::forward<_T2>(__rhs);
  }

  using is_transparent = void;
};

template <class _Tp = void>
struct modulus {
  _ASCEND_AICORE_FN constexpr _Tp operator()(const _Tp& __lhs, const _Tp& __rhs) const
  {
    return __lhs % __rhs;
  }
};

template <>
struct modulus<void> {
  template <class _T1, class _T2>
  _ASCEND_AICORE_FN constexpr auto operator()(_T1&& __lhs, _T2&& __rhs) const
      -> decltype(_ASCEND_STD::forward<_T1>(__lhs) % _ASCEND_STD::forward<_T2>(__rhs))
  {
    return _ASCEND_STD::forward<_T1>(__lhs) % _ASCEND_STD::forward<_T2>(__rhs);
  }

  using is_transparent = void;
};

template <class _Tp = void>
struct negate {
  _ASCEND_AICORE_FN constexpr _Tp operator()(const _Tp& __value) const
  {
    return -__value;
  }
};

template <>
struct negate<void> {
  template <class _Tp>
  _ASCEND_AICORE_FN constexpr auto operator()(_Tp&& __value) const -> decltype(-_ASCEND_STD::forward<_Tp>(__value))
  {
    return -_ASCEND_STD::forward<_Tp>(__value);
  }

  using is_transparent = void;
};

template <class _Tp = void>
struct equal_to {
  _ASCEND_AICORE_FN constexpr bool operator()(const _Tp& __lhs, const _Tp& __rhs) const
  {
    return __lhs == __rhs;
  }
};

template <>
struct equal_to<void> {
  template <class _T1, class _T2>
  _ASCEND_AICORE_FN constexpr auto operator()(_T1&& __lhs, _T2&& __rhs) const
      -> decltype(_ASCEND_STD::forward<_T1>(__lhs) == _ASCEND_STD::forward<_T2>(__rhs))
  {
    return _ASCEND_STD::forward<_T1>(__lhs) == _ASCEND_STD::forward<_T2>(__rhs);
  }

  using is_transparent = void;
};

template <class _Tp = void>
struct less {
  _ASCEND_AICORE_FN constexpr bool operator()(const _Tp& __lhs, const _Tp& __rhs) const
  {
    return __lhs < __rhs;
  }
};

template <>
struct less<void> {
  template <class _T1, class _T2>
  _ASCEND_AICORE_FN constexpr auto operator()(_T1&& __lhs, _T2&& __rhs) const
      -> decltype(_ASCEND_STD::forward<_T1>(__lhs) < _ASCEND_STD::forward<_T2>(__rhs))
  {
    return _ASCEND_STD::forward<_T1>(__lhs) < _ASCEND_STD::forward<_T2>(__rhs);
  }

  using is_transparent = void;
};

template <class _Tp = void>
struct greater {
  _ASCEND_AICORE_FN constexpr bool operator()(const _Tp& __lhs, const _Tp& __rhs) const
  {
    return __rhs < __lhs;
  }
};

template <>
struct greater<void> {
  template <class _T1, class _T2>
  _ASCEND_AICORE_FN constexpr auto operator()(_T1&& __lhs, _T2&& __rhs) const
      -> decltype(_ASCEND_STD::forward<_T2>(__rhs) < _ASCEND_STD::forward<_T1>(__lhs))
  {
    return _ASCEND_STD::forward<_T2>(__rhs) < _ASCEND_STD::forward<_T1>(__lhs);
  }

  using is_transparent = void;
};

_ASCEND_STD_END

#endif  // LIBASCENDCXX_INCLUDE_ASCEND_STD___FUNCTIONAL_OPERATIONS_H_
