#ifndef LIBASCENDCXX_INCLUDE_ASCEND_STD___ALGORITHM_MINMAX_H_
#define LIBASCENDCXX_INCLUDE_ASCEND_STD___ALGORITHM_MINMAX_H_

#include "ascend/std/__config"
#include "ascend/std/__utility/pair.h"

#if defined(__CCE__)
#define ASCEND_DEVICE_CODE
#endif

_ASCEND_STD_BEGIN

// Returns {min, max} as a pair of const references. If __a and __b are
// equivalent, the pair is {__a, __b} (i.e. ties keep the original order).
template <typename _Tp>
_ASCEND_AICORE_FN constexpr pair<const _Tp&, const _Tp&> minmax(const _Tp& __a, const _Tp& __b) {
    return (__b < __a) ? pair<const _Tp&, const _Tp&>(__b, __a) : pair<const _Tp&, const _Tp&>(__a, __b);
}

template <typename _Tp, typename _Compare>
// NOLINTNEXTLINE
_ASCEND_AICORE_FN constexpr pair<const _Tp&, const _Tp&> minmax(const _Tp& __a, const _Tp& __b, _Compare __comp) {
    return __comp(__b, __a) ? pair<const _Tp&, const _Tp&>(__b, __a) : pair<const _Tp&, const _Tp&>(__a, __b);
}

_ASCEND_STD_END

#endif  // LIBASCENDCXX_INCLUDE_ASCEND_STD___ALGORITHM_MINMAX_H_
