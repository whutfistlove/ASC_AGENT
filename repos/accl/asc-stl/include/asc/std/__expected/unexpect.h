#ifndef ASC_STL_INCLUDE_ASC_STD___EXPECTED_UNEXPECT_H_
#define ASC_STL_INCLUDE_ASC_STD___EXPECTED_UNEXPECT_H_

#include "asc/std/__config"

#if defined(__CCE__)
#define ASC_DEVICE_CODE
#endif

_ASC_STD_BEGIN

struct unexpect_t
{
  explicit unexpect_t() = default;
};

inline constexpr unexpect_t unexpect{};

_ASC_STD_END

#endif // ASC_STL_INCLUDE_ASC_STD___EXPECTED_UNEXPECT_H_
