#ifndef LIBASCENDCXX_INCLUDE_ASCEND_STD___TYPE_TRAITS_IS_REFERENCE_H_
#define LIBASCENDCXX_INCLUDE_ASCEND_STD___TYPE_TRAITS_IS_REFERENCE_H_

#include "ascend/std/__type_traits/integral_constant.h"

_ASCEND_STD_BEGIN

template <class _Tp>
struct is_lvalue_reference : false_type {};

template <class _Tp>
struct is_lvalue_reference<_Tp&> : true_type {};

template <class _Tp>
inline constexpr bool is_lvalue_reference_v = is_lvalue_reference<_Tp>::value;

template <class _Tp>
struct is_rvalue_reference : false_type {};

template <class _Tp>
struct is_rvalue_reference<_Tp&&> : true_type {};

template <class _Tp>
inline constexpr bool is_rvalue_reference_v = is_rvalue_reference<_Tp>::value;

template <class _Tp>
struct is_reference : false_type {};

template <class _Tp>
struct is_reference<_Tp&> : true_type {};

template <class _Tp>
struct is_reference<_Tp&&> : true_type {};

template <class _Tp>
inline constexpr bool is_reference_v = is_reference<_Tp>::value;

_ASCEND_STD_END

#endif  // LIBASCENDCXX_INCLUDE_ASCEND_STD___TYPE_TRAITS_IS_REFERENCE_H_
