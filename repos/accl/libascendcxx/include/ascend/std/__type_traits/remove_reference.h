#ifndef LIBASCENDCXX_INCLUDE_ASCEND_STD___TYPE_TRAITS_REMOVE_REFERENCE_H_
#define LIBASCENDCXX_INCLUDE_ASCEND_STD___TYPE_TRAITS_REMOVE_REFERENCE_H_

#include "ascend/std/__config"

_ASCEND_STD_BEGIN

template <class _Tp>
struct remove_reference {
  using type = _Tp;
};

template <class _Tp>
struct remove_reference<_Tp&> {
  using type = _Tp;
};

template <class _Tp>
struct remove_reference<_Tp&&> {
  using type = _Tp;
};

template <class _Tp>
using remove_reference_t = typename remove_reference<_Tp>::type;

_ASCEND_STD_END

#endif  // LIBASCENDCXX_INCLUDE_ASCEND_STD___TYPE_TRAITS_REMOVE_REFERENCE_H_
