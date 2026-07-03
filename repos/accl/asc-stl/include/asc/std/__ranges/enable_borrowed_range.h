#ifndef ASC_STL_INCLUDE_ASC_STD___RANGES_ENABLE_BORROWED_RANGE_H_
#define ASC_STL_INCLUDE_ASC_STD___RANGES_ENABLE_BORROWED_RANGE_H_

// These customization variables are used in <span> and <string_view>. The
// separate header is used to avoid including the entire <ranges> header in
// <span> and <string_view>.

#include "asc/std/__config"

#if defined(__CCE__)
#define ASC_DEVICE_CODE
#endif

_ASC_STD_BEGIN

// [range.range], ranges

template <class>
inline constexpr bool enable_borrowed_range = false;

_ASC_STD_END

#endif // ASC_STL_INCLUDE_ASC_STD___RANGES_ENABLE_BORROWED_RANGE_H_
