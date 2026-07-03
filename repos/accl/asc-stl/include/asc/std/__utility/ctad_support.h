#ifndef ASC_STL_INCLUDE_ASC_STD___UTILITY_CTAD_SUPPORT_H_
#define ASC_STL_INCLUDE_ASC_STD___UTILITY_CTAD_SUPPORT_H_

#include "asc/std/__config"

#if defined(__CCE__)
#define ASC_DEVICE_CODE
#endif

#define _ASC_CTAD_SUPPORTED_FOR_TYPE(_ClassName) \
  template <class... _Tag>                        \
  _ClassName(typename _Tag::__allow_ctad...)->_ClassName<_Tag...>

#endif // ASC_STL_INCLUDE_ASC_STD___UTILITY_CTAD_SUPPORT_H_
