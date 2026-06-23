#ifndef ASC_STL_INCLUDE_ASC_STD___ALGORITHM_FOR_EACH_H_
#define ASC_STL_INCLUDE_ASC_STD___ALGORITHM_FOR_EACH_H_

#include "asc/std/__config"

#if defined(__CCE__)
#define ASC_DEVICE_CODE
#endif

_ASC_STD_BEGIN

template <typename _InputIterator, typename _Function>
_ASC_AICORE_FN constexpr _Function for_each(_InputIterator __first, _InputIterator __last, _Function __f)
{
  for (; __first != __last; ++__first)
  {
    __f(*__first);
  }
  return __f;
}

_ASC_STD_END

#endif // ASC_STL_INCLUDE_ASC_STD___ALGORITHM_FOR_EACH_H_
