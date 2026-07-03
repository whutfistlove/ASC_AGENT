#ifndef ASC_STL_INCLUDE_ASC_STD___ITERATOR_DEFAULT_SENTINEL_H_
#define ASC_STL_INCLUDE_ASC_STD___ITERATOR_DEFAULT_SENTINEL_H_

#include "asc/std/__config"

#if defined(__CCE__)
#define ASC_DEVICE_CODE
#endif

_ASC_STD_BEGIN

struct default_sentinel_t
{};
inline constexpr default_sentinel_t default_sentinel{};

_ASC_STD_END

#endif // ASC_STL_INCLUDE_ASC_STD___ITERATOR_DEFAULT_SENTINEL_H_
