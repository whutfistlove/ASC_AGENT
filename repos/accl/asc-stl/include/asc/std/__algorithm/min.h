#ifndef ASC_STL_INCLUDE_ASC_STD___ALGORITHM_MIN_H_
#define ASC_STL_INCLUDE_ASC_STD___ALGORITHM_MIN_H_

#include "asc/std/__config"

#if defined(__CCE__)
#define ASC_DEVICE_CODE
#endif

_ASC_STD_BEGIN

// Primary template using operator<
template <typename _Tp>
_ASC_AICORE_FN constexpr const _Tp& min(const _Tp& __a, const _Tp& __b) {
    return (__b < __a) ? __b : __a;
}

template <typename _Tp, typename _Compare>
// NOLINTNEXTLINE
_ASC_AICORE_FN constexpr const _Tp& min(const _Tp& __a, const _Tp& __b, _Compare __comp) {
    return __comp(__b, __a) ? __b : __a;
}

_ASC_STD_END

#endif  // ASC_STL_INCLUDE_ASC_STD___ALGORITHM_MIN_H_
