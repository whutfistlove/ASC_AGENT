#ifndef ASC_STL_INCLUDE_ASC_STD___ALGORITHM_REVERSE_COPY_H_
#define ASC_STL_INCLUDE_ASC_STD___ALGORITHM_REVERSE_COPY_H_

#include "asc/std/__config"

#if defined(__CCE__)
#define ASC_DEVICE_CODE
#endif

_ASC_STD_BEGIN

template <typename _BidirectionalIterator, typename _OutputIterator>
_ASC_AICORE_FN constexpr _OutputIterator
reverse_copy(_BidirectionalIterator __first, _BidirectionalIterator __last, _OutputIterator __result)
{
  for (; __first != __last; ++__result)
  {
    *__result = *--__last;
  }
  return __result;
}

_ASC_STD_END

#endif // ASC_STL_INCLUDE_ASC_STD___ALGORITHM_REVERSE_COPY_H_
