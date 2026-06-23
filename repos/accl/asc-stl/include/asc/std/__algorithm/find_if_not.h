#ifndef ASC_STL_INCLUDE_ASC_STD___ALGORITHM_FIND_IF_NOT_H_
#define ASC_STL_INCLUDE_ASC_STD___ALGORITHM_FIND_IF_NOT_H_

#include "asc/std/__config"

#if defined(__CCE__)
#define ASC_DEVICE_CODE
#endif

_ASC_STD_BEGIN

template <typename _InputIterator, typename _Predicate>
_ASC_AICORE_FN constexpr _InputIterator
find_if_not(_InputIterator __first, _InputIterator __last, _Predicate __pred)
{
  for (; __first != __last; ++__first)
  {
    if (!__pred(*__first))
    {
      break;
    }
  }
  return __first;
}

_ASC_STD_END

#endif // ASC_STL_INCLUDE_ASC_STD___ALGORITHM_FIND_IF_NOT_H_
