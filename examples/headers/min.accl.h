/******************************************************************************
 * Copyright (c) 2025 AISS Group at Harbin Institute of Technology. All Rights Reserved.
 * Author: Luxiongbo <luxiongbo@whut.edu.cn>
 * Create: 2026-01-18
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *****************************************************************************/

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

// todo
// // Initializer list version (C++11+)
// template <typename _Tp>
// _ASC_AICORE_FN constexpr _Tp min(::std::initializer_list<_Tp> __il)
// {
//     return *::std::min_element(__il.begin(), __il.end());
// }

// // Initializer list with comparator
// template <typename _Tp, typename _Compare>
// _ASC_AICORE_FN constexpr _Tp min(::std::initializer_list<_Tp> __il, _Compare __comp)
// {
//     return *::std::min_element(__il.begin(), __il.end(), __comp);
// }

_ASC_STD_END

#endif  // ASC_STL_INCLUDE_ASC_STD___ALGORITHM_MIN_H_
