#ifndef LIBASCENDCXX_INCLUDE_ASCEND_STD___ALGORITHM_CLAMP_H_
#define LIBASCENDCXX_INCLUDE_ASCEND_STD___ALGORITHM_CLAMP_H_

#include "ascend/std/__config"

#if defined(__CCE__)
#define ASCEND_DEVICE_CODE
#endif

_ASCEND_STD_BEGIN

template <typename _Tp>
_ASCEND_AICORE_FN constexpr const _Tp& clamp(const _Tp& __v, const _Tp& __lo, const _Tp& __hi) {
    return (__v < __lo) ? __lo : (__hi < __v) ? __hi : __v;
}

template <typename _Tp, typename _Compare>
// NOLINTNEXTLINE
_ASCEND_AICORE_FN constexpr const _Tp& clamp(const _Tp& __v, const _Tp& __lo, const _Tp& __hi, _Compare __comp) {
    return __comp(__v, __lo) ? __lo : __comp(__hi, __v) ? __hi : __v;
}

_ASCEND_STD_END

#endif  // LIBASCENDCXX_INCLUDE_ASCEND_STD___ALGORITHM_CLAMP_H_
