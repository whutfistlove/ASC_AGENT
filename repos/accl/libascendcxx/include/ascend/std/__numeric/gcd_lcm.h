#ifndef LIBASCENDCXX_INCLUDE_ASCEND_STD___NUMERIC_GCD_LCM_H_
#define LIBASCENDCXX_INCLUDE_ASCEND_STD___NUMERIC_GCD_LCM_H_

#include "ascend/std/__config"
#include <type_traits>

_ASCEND_STD_BEGIN

template <class _Tp>
_ASCEND_AICORE_FN constexpr _Tp __gcd_unsigned(_Tp __m, _Tp __n)
{
    static_assert(!::std::is_signed<_Tp>::value, "__gcd_unsigned requires an unsigned type");
    while (__n != 0) {
        _Tp __t = static_cast<_Tp>(__m % __n);
        __m = __n;
        __n = __t;
    }
    return __m;
}

template <class _Rp, class _Tp>
_ASCEND_AICORE_FN constexpr typename ::std::make_unsigned<_Rp>::type __abs_to_unsigned(_Tp __v)
{
    using _Up = typename ::std::make_unsigned<_Rp>::type;
    if constexpr (::std::is_signed<_Tp>::value) {
        return __v < 0 ? static_cast<_Up>(_Up(0) - static_cast<_Up>(__v)) : static_cast<_Up>(__v);
    } else {
        return static_cast<_Up>(__v);
    }
}

template <class _Tp, class _Up>
_ASCEND_AICORE_FN constexpr typename ::std::common_type<_Tp, _Up>::type gcd(_Tp __m, _Up __n)
{
    static_assert(::std::is_integral<_Tp>::value && ::std::is_integral<_Up>::value,
                  "Arguments to gcd must be integer types");
    static_assert(!::std::is_same<typename ::std::remove_cv<_Tp>::type, bool>::value,
                  "First argument to gcd cannot be bool");
    static_assert(!::std::is_same<typename ::std::remove_cv<_Up>::type, bool>::value,
                  "Second argument to gcd cannot be bool");

    using _Rp = typename ::std::common_type<_Tp, _Up>::type;
    using _Wp = typename ::std::make_unsigned<_Rp>::type;
    return static_cast<_Rp>(
        _ASCEND_STD::__gcd_unsigned<_Wp>(_ASCEND_STD::__abs_to_unsigned<_Rp>(__m),
                                         _ASCEND_STD::__abs_to_unsigned<_Rp>(__n)));
}

template <class _Tp, class _Up>
_ASCEND_AICORE_FN constexpr typename ::std::common_type<_Tp, _Up>::type lcm(_Tp __m, _Up __n)
{
    static_assert(::std::is_integral<_Tp>::value && ::std::is_integral<_Up>::value,
                  "Arguments to lcm must be integer types");
    static_assert(!::std::is_same<typename ::std::remove_cv<_Tp>::type, bool>::value,
                  "First argument to lcm cannot be bool");
    static_assert(!::std::is_same<typename ::std::remove_cv<_Up>::type, bool>::value,
                  "Second argument to lcm cannot be bool");

    if (__m == 0 || __n == 0) {
        return 0;
    }

    using _Rp = typename ::std::common_type<_Tp, _Up>::type;
    using _Wp = typename ::std::make_unsigned<_Rp>::type;
    const _Wp __m_abs = _ASCEND_STD::__abs_to_unsigned<_Rp>(__m);
    const _Wp __n_abs = _ASCEND_STD::__abs_to_unsigned<_Rp>(__n);
    const _Wp __g = _ASCEND_STD::__abs_to_unsigned<_Rp>(_ASCEND_STD::gcd(__m, __n));
    return static_cast<_Rp>((__m_abs / __g) * __n_abs);
}

_ASCEND_STD_END

#endif  // LIBASCENDCXX_INCLUDE_ASCEND_STD___NUMERIC_GCD_LCM_H_
