#ifndef ASC_STL_INCLUDE_ASC_STD___ALGORITHM_GENERATE_H_
#define ASC_STL_INCLUDE_ASC_STD___ALGORITHM_GENERATE_H_

#include "asc/std/__config"

#if defined(__CCE__)
#define ASC_DEVICE_CODE
#endif

_ASC_STD_BEGIN

template <typename _ForwardIterator, typename _Generator>
_ASC_AICORE_FN constexpr void generate(_ForwardIterator __first, _ForwardIterator __last, _Generator __gen)
{
  for (; __first != __last; ++__first)
  {
    *__first = __gen();
  }
}

_ASC_STD_END

#endif // ASC_STL_INCLUDE_ASC_STD___ALGORITHM_GENERATE_H_
