#ifndef LIBASCENDCXX_INCLUDE_ASCEND_STD___NUMERIC_MIDPOINT_H_
#define LIBASCENDCXX_INCLUDE_ASCEND_STD___NUMERIC_MIDPOINT_H_

#include "ascend/std/__config"
#include <cstddef>
#include <limits>
#include <type_traits>

_ASCEND_STD_BEGIN

template <class _Tp>
_ASCEND_AICORE_FN constexpr typename ::std::enable_if<
    ::std::is_integral<_Tp>::value && !::std::is_same<typename ::std::remove_cv<_Tp>::type, bool>::value,
    _Tp>::type
midpoint(_Tp __a, _Tp __b) noexcept
{
    using _Up = typename ::std::make_unsigned<_Tp>::type;

    if (__a > __b) {
        const _Up __diff = static_cast<_Up>(__a) - static_cast<_Up>(__b);
        return static_cast<_Tp>(__a - static_cast<_Tp>(__diff / 2));
    }

    const _Up __diff = static_cast<_Up>(__b) - static_cast<_Up>(__a);
    return static_cast<_Tp>(__a + static_cast<_Tp>(__diff / 2));
}

template <class _Tp>
_ASCEND_AICORE_FN constexpr typename ::std::enable_if<
    ::std::is_object<_Tp>::value && !::std::is_void<_Tp>::value && (sizeof(_Tp) > 0),
    _Tp*>::type
midpoint(_Tp* __a, _Tp* __b) noexcept
{
    return __a + _ASCEND_STD::midpoint(static_cast<::std::ptrdiff_t>(0), __b - __a);
}

template <class _Tp>
_ASCEND_AICORE_FN constexpr _Tp __fp_abs(_Tp __v)
{
    return __v >= _Tp(0) ? __v : -__v;
}

template <class _Tp>
_ASCEND_AICORE_FN constexpr typename ::std::enable_if<::std::is_floating_point<_Tp>::value, _Tp>::type
midpoint(_Tp __a, _Tp __b) noexcept
{
    constexpr _Tp __lo = (::std::numeric_limits<_Tp>::min)() * _Tp(2);
    constexpr _Tp __hi = (::std::numeric_limits<_Tp>::max)() / _Tp(2);

    return _ASCEND_STD::__fp_abs(__a) <= __hi && _ASCEND_STD::__fp_abs(__b) <= __hi
               ? (__a + __b) / _Tp(2)
               : _ASCEND_STD::__fp_abs(__a) < __lo
                     ? __a + __b / _Tp(2)
                     : _ASCEND_STD::__fp_abs(__b) < __lo ? __a / _Tp(2) + __b : __a / _Tp(2) + __b / _Tp(2);
}

_ASCEND_STD_END

#endif  // LIBASCENDCXX_INCLUDE_ASCEND_STD___NUMERIC_MIDPOINT_H_
