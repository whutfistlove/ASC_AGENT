#ifndef ASC_STL_INCLUDE_ASC_STD___TYPE_TRAITS_NAT_H_
#define ASC_STL_INCLUDE_ASC_STD___TYPE_TRAITS_NAT_H_

#include "asc/std/__config"

#if defined(__CCE__)
#define ASC_DEVICE_CODE
#endif

_ASC_STD_BEGIN

struct __nat
{
  __nat()                        = delete;
  __nat(const __nat&)            = delete;
  __nat& operator=(const __nat&) = delete;
  ~__nat()                       = delete;
};

_ASC_STD_END

#endif // ASC_STL_INCLUDE_ASC_STD___TYPE_TRAITS_NAT_H_
