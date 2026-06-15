#ifndef ASC_STL_INCLUDE_ASC_STD___TYPE_TRAITS_INTEGRAL_CONSTANT_H_
#define ASC_STL_INCLUDE_ASC_STD___TYPE_TRAITS_INTEGRAL_CONSTANT_H_

#include "asc/std/__config"

#if defined(__CCE__)
#define ASC_DEVICE_CODE
#endif

_ASC_STD_BEGIN

template <class _Tp, _Tp __v>
struct integral_constant
{
  static constexpr const _Tp value = __v;
  using value_type                 = _Tp;
  using type                       = integral_constant;
  _ASC_AICORE_FN constexpr operator value_type() const noexcept
  {
    return value;
  }
  _ASC_AICORE_FN constexpr value_type operator()() const noexcept
  {
    return value;
  }
};

using true_type  = integral_constant<bool, true>;
using false_type = integral_constant<bool, false>;

template <bool __b>
using bool_constant = integral_constant<bool, __b>;

_ASC_STD_END

#endif // ASC_STL_INCLUDE_ASC_STD___TYPE_TRAITS_INTEGRAL_CONSTANT_H_
