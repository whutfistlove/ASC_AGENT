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

#ifndef LIBASCENDCXX_INCLUDE_ASCEND_STD___ACCL_OS_H_  // NOLINT(build/header_guard)
#define LIBASCENDCXX_INCLUDE_ASCEND_STD___ACCL_OS_H_

// The header provides the following macros to determine the host architecture:
//
// _ACCL_OS(WINDOWS)
// _ACCL_OS(LINUX)
// _ACCL_OS(ANDROID)
// _ACCL_OS(QNX)
// _ACCL_OS(APPLE)
// _ACCL_OS(HARMONY)

// Determine the host OS and its presence
#if defined(_WIN32) || defined(_WIN64) /* _WIN64 for NVRTC */
#define _ACCL_OS_WINDOWS_() 1
#else
#define _ACCL_OS_WINDOWS_() 0
#endif

#if defined(__linux__) || defined(__LP64__) /* __LP64__ for NVRTC */
#define _ACCL_OS_LINUX_() 1
#else
#define _ACCL_OS_LINUX_() 0
#endif

#if defined(__ANDROID__)
#define _ACCL_OS_ANDROID_() 1
#else
#define _ACCL_OS_ANDROID_() 0
#endif

#if defined(__OHOS__) || defined(__OPENHARMONY__)
#define _ACCL_OS_HARMONY_() 1
#else
#define _ACCL_OS_HARMONY_() 0
#endif

#if defined(__QNX__) || defined(__QNXNTO__)
#define _ACCL_OS_QNX_() 1
#else
#define _ACCL_OS_QNX_() 0
#endif

#if defined(__APPLE__) || defined(__APPLE_CC__)
#define _ACCL_OS_APPLE_() 1
#else
#define _ACCL_OS_APPLE_() 0
#endif

#define _ACCL_OS(...) _ACCL_OS_##__VA_ARGS__##_()

#endif  // LIBASCENDCXX_INCLUDE_ASCEND_STD___ACCL_OS_H_