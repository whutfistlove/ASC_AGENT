#ifndef LIBASCENDCXX_INCLUDE_ASCEND_STD___ALGORITHM_MIN_H_
#define LIBASCENDCXX_INCLUDE_ASCEND_STD___ALGORITHM_MIN_H_

#include "ascend/std/__config"

#if defined(__CCE__)
#define ASCEND_DEVICE_CODE
#endif

_ASCEND_STD_BEGIN

// Primary template using std::less
template <typename _Tp>
_ASCEND_AICORE_FN constexpr const _Tp& min(const _Tp& __a, const _Tp& __b) {
    return (__b < __a) ? __b : __a;
}

template <typename _Tp, typename _Compare>
// NOLINTNEXTLINE
_ASCEND_AICORE_FN constexpr const _Tp& min(const _Tp& __a, const _Tp& __b, _Compare __comp) {
    return __comp(__b, __a) ? __b : __a;
}

_ASCEND_STD_END

#endif  // LIBASCENDCXX_INCLUDE_ASCEND_STD___ALGORITHM_MIN_H_
