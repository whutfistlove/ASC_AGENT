#ifndef ASC_STL_INCLUDE_ASC_STD___TYPE_TRAITS_VOID_T_H_
#define ASC_STL_INCLUDE_ASC_STD___TYPE_TRAITS_VOID_T_H_

#include "asc/std/__config"

#if defined(__CCE__)
#define ASC_DEVICE_CODE
#endif

_ASC_STD_BEGIN

template <class...>
using void_t = void;

_ASC_STD_END

#endif // ASC_STL_INCLUDE_ASC_STD___TYPE_TRAITS_VOID_T_H_
