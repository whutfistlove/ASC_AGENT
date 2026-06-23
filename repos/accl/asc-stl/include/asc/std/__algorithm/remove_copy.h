#ifndef ASC_STL_INCLUDE_ASC_STD___ALGORITHM_REMOVE_COPY_H_
#define ASC_STL_INCLUDE_ASC_STD___ALGORITHM_REMOVE_COPY_H_

#include "asc/std/__config"

#if defined(__CCE__)
#define ASC_DEVICE_CODE
#endif

_ASC_STD_BEGIN

template <typename _InputIterator, typename _OutputIterator, typename _Tp>
_ASC_AICORE_FN constexpr _OutputIterator
remove_copy(_InputIterator __first, _InputIterator __last, _OutputIterator __result, const _Tp& __value_)
{
  for (; __first != __last; ++__first)
  {
    if (!(*__first == __value_))
    {
      *__result = *__first;
      ++__result;
    }
  }
  return __result;
}

_ASC_STD_END

#endif // ASC_STL_INCLUDE_ASC_STD___ALGORITHM_REMOVE_COPY_H_
