#ifndef ASC_STL_INCLUDE_ASC_STD___BARRIER_EMPTY_COMPLETION_H_
#define ASC_STL_INCLUDE_ASC_STD___BARRIER_EMPTY_COMPLETION_H_

#include "asc/std/__config"

#if defined(__CCE__)
#define ASC_DEVICE_CODE
#endif

_ASC_STD_BEGIN

struct __empty_completion
{
  _ASC_AICORE_FN constexpr void operator()() noexcept {}
};

_ASC_STD_END

#endif // ASC_STL_INCLUDE_ASC_STD___BARRIER_EMPTY_COMPLETION_H_
