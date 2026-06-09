#ifndef LIBASCENDCXX_INCLUDE_ASCEND_STD___TYPE_TRAITS_CONDITIONAL_H_
#define LIBASCENDCXX_INCLUDE_ASCEND_STD___TYPE_TRAITS_CONDITIONAL_H_

#include "ascend/std/__config"

_ASCEND_STD_BEGIN

template <bool _Bp, class _If, class _Then>
struct conditional {
  using type = _If;
};

template <class _If, class _Then>
struct conditional<false, _If, _Then> {
  using type = _Then;
};

template <bool _Bp, class _If, class _Then>
using conditional_t = typename conditional<_Bp, _If, _Then>::type;

_ASCEND_STD_END

#endif  // LIBASCENDCXX_INCLUDE_ASCEND_STD___TYPE_TRAITS_CONDITIONAL_H_
