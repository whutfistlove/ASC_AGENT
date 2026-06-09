#ifndef LIBASCENDCXX_INCLUDE_ASCEND_STD___TYPE_TRAITS_INTEGRAL_CONSTANT_H_
#define LIBASCENDCXX_INCLUDE_ASCEND_STD___TYPE_TRAITS_INTEGRAL_CONSTANT_H_

#include "ascend/std/__config"

_ASCEND_STD_BEGIN

template <class _Tp, _Tp __v>
struct integral_constant {
  static constexpr _Tp value = __v;
  using value_type = _Tp;
  using type = integral_constant;

  _ASCEND_AICORE_FN constexpr operator value_type() const noexcept { return value; }
  _ASCEND_AICORE_FN constexpr value_type operator()() const noexcept { return value; }
};

template <bool __v>
using bool_constant = integral_constant<bool, __v>;

using true_type = bool_constant<true>;
using false_type = bool_constant<false>;

_ASCEND_STD_END

#endif  // LIBASCENDCXX_INCLUDE_ASCEND_STD___TYPE_TRAITS_INTEGRAL_CONSTANT_H_
