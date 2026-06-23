#ifndef ASC_STL_INCLUDE_ASC_STD___ALGORITHM_NONE_OF_H_
#define ASC_STL_INCLUDE_ASC_STD___ALGORITHM_NONE_OF_H_

#include "asc/std/__config"

#if defined(__CCE__)
#define ASC_DEVICE_CODE
#endif

_ASC_STD_BEGIN

template <typename _InputIterator, typename _Predicate>
_ASC_AICORE_FN constexpr bool none_of(_InputIterator __first, _InputIterator __last, _Predicate __pred)
{
  bool __result = true;
  for (; __first != __last; ++__first)
  {
    if (__pred(*__first))
    {
      __result = false;
      break;
    }
  }
  return __result;
}

_ASC_STD_END

#endif // ASC_STL_INCLUDE_ASC_STD___ALGORITHM_NONE_OF_H_
