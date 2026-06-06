#ifndef LIBASCENDCXX_INCLUDE_ASCEND_STD___TYPE_TRAITS_IS_SAME_H_
#define LIBASCENDCXX_INCLUDE_ASCEND_STD___TYPE_TRAITS_IS_SAME_H_

#include "ascend/std/__type_traits/integral_constant.h"

_ASCEND_STD_BEGIN

template <class _Tp, class _Up>
struct is_same : false_type {};

template <class _Tp>
struct is_same<_Tp, _Tp> : true_type {};

template <class _Tp, class _Up>
inline constexpr bool is_same_v = is_same<_Tp, _Up>::value;

_ASCEND_STD_END

#endif  // LIBASCENDCXX_INCLUDE_ASCEND_STD___TYPE_TRAITS_IS_SAME_H_
