#ifndef LIBASCENDCXX_INCLUDE_ASCEND_STD___ALGORITHM_NONE_OF_H_
#define LIBASCENDCXX_INCLUDE_ASCEND_STD___ALGORITHM_NONE_OF_H_

#include "ascend/std/__config"

#if defined(__CCE__)
#define ASCEND_DEVICE_CODE
#endif

_ASCEND_STD_BEGIN

template <typename _InputIterator, typename _Predicate>
_ASCEND_AICORE_FN constexpr bool none_of(_InputIterator __first, _InputIterator __last, _Predicate __pred)
{
    for (; __first != __last; ++__first)
    {
        if (__pred(*__first))
        {
            return false;
        }
    }
    return true;
}

_ASCEND_STD_END

#endif  // LIBASCENDCXX_INCLUDE_ASCEND_STD___ALGORITHM_NONE_OF_H_
