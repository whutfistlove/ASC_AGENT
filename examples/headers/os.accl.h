/******************************************************************************
 * Copyright (c) 2026 Xiong Shengwu Group at Wuhan University of Technology. All Rights Reserved.
 * Author: Zhenyu Jiang <2786369597@qq.com>
 * Create: 2026-01-23
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

#ifndef ASC_STL_INCLUDE_ASC_STD___ASC_OS_H_  // NOLINT(build/header_guard)
#define ASC_STL_INCLUDE_ASC_STD___ASC_OS_H_

// The header provides the following macros to determine the host architecture:
//
// _ASC_OS(WINDOWS)
// _ASC_OS(LINUX)
// _ASC_OS(ANDROID)
// _ASC_OS(QNX)
// _ASC_OS(APPLE)
// _ASC_OS(HARMONY)

// Determine the host OS and its presence
#if defined(_WIN32) || defined(_WIN64) /* _WIN64 for NVRTC */
#define _ASC_OS_WINDOWS_() 1
#else
#define _ASC_OS_WINDOWS_() 0
#endif

#if defined(__linux__) || defined(__LP64__) /* __LP64__ for NVRTC */
#define _ASC_OS_LINUX_() 1
#else
#define _ASC_OS_LINUX_() 0
#endif

#if defined(__ANDROID__)
#define _ASC_OS_ANDROID_() 1
#else
#define _ASC_OS_ANDROID_() 0
#endif

#if defined(__OHOS__) || defined(__OPENHARMONY__)
#define _ASC_OS_HARMONY_() 1
#else
#define _ASC_OS_HARMONY_() 0
#endif

#if defined(__QNX__) || defined(__QNXNTO__)
#define _ASC_OS_QNX_() 1
#else
#define _ASC_OS_QNX_() 0
#endif

#if defined(__APPLE__) || defined(__APPLE_CC__)
#define _ASC_OS_APPLE_() 1
#else
#define _ASC_OS_APPLE_() 0
#endif

#define _ASC_OS(...) _ASC_OS_##__VA_ARGS__##_()

#endif  // ASC_STL_INCLUDE_ASC_STD___ASC_OS_H_