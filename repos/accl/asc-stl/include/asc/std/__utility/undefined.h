#ifndef ASC_STL_INCLUDE_ASC_STD___UTILITY_UNDEFINED_H_
#define ASC_STL_INCLUDE_ASC_STD___UTILITY_UNDEFINED_H_

#include "asc/std/__config"

#if defined(__CCE__)
#define ASC_DEVICE_CODE
#endif

_ASC_STD_BEGIN

template <typename...>
struct __undefined; // leave this undefined

_ASC_STD_END

#endif // ASC_STL_INCLUDE_ASC_STD___UTILITY_UNDEFINED_H_
