#ifndef ASC_STL_INCLUDE_ASC_STD___ALGORITHM_REMOVE_COPY_IF_H_
#define ASC_STL_INCLUDE_ASC_STD___ALGORITHM_REMOVE_COPY_IF_H_

#include "asc/std/__config"

#if defined(__CCE__)
#define ASC_DEVICE_CODE
#endif

_ASC_STD_BEGIN

template <typename _InputIterator, typename _OutputIterator, typename _Predicate>
_ASC_AICORE_FN constexpr _OutputIterator
remove_copy_if(_InputIterator __first, _InputIterator __last, _OutputIterator __result, _Predicate __pred)
{
  for (; __first != __last; ++__first)
  {
    if (!__pred(*__first))
    {
      *__result = *__first;
      ++__result;
    }
  }
  return __result;
}

_ASC_STD_END

#endif // ASC_STL_INCLUDE_ASC_STD___ALGORITHM_REMOVE_COPY_IF_H_
