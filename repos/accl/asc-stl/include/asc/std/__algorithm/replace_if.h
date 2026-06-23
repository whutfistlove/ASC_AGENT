#ifndef ASC_STL_INCLUDE_ASC_STD___ALGORITHM_REPLACE_IF_H_
#define ASC_STL_INCLUDE_ASC_STD___ALGORITHM_REPLACE_IF_H_

#include "asc/std/__config"

#if defined(__CCE__)
#define ASC_DEVICE_CODE
#endif

_ASC_STD_BEGIN

template <typename _ForwardIterator, typename _Predicate, typename _Tp>
_ASC_AICORE_FN constexpr void
replace_if(_ForwardIterator __first, _ForwardIterator __last, _Predicate __pred, const _Tp& __new_value)
{
  for (; __first != __last; ++__first)
  {
    if (__pred(*__first))
    {
      *__first = __new_value;
    }
  }
}

_ASC_STD_END

#endif // ASC_STL_INCLUDE_ASC_STD___ALGORITHM_REPLACE_IF_H_
