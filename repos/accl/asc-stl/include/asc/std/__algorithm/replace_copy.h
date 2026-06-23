#ifndef ASC_STL_INCLUDE_ASC_STD___ALGORITHM_REPLACE_COPY_H_
#define ASC_STL_INCLUDE_ASC_STD___ALGORITHM_REPLACE_COPY_H_

#include "asc/std/__config"

#if defined(__CCE__)
#define ASC_DEVICE_CODE
#endif

_ASC_STD_BEGIN

template <typename _InputIterator, typename _OutputIterator, typename _Tp>
_ASC_AICORE_FN constexpr _OutputIterator replace_copy(
  _InputIterator __first,
  _InputIterator __last,
  _OutputIterator __result,
  const _Tp& __old_value,
  const _Tp& __new_value)
{
  for (; __first != __last; ++__first, ++__result)
  {
    if (*__first == __old_value)
    {
      *__result = __new_value;
    }
    else
    {
      *__result = *__first;
    }
  }
  return __result;
}

_ASC_STD_END

#endif // ASC_STL_INCLUDE_ASC_STD___ALGORITHM_REPLACE_COPY_H_
