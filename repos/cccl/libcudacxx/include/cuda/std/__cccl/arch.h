//===----------------------------------------------------------------------===//
//
// Part of libcu++, the C++ Standard Library for your entire system,
// under the Apache License v2.0 with LLVM Exceptions.
// See https://llvm.org/LICENSE.txt for license information.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
// SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES.
//
//===----------------------------------------------------------------------===//

#ifndef __CCCL_ARCH_H
#define __CCCL_ARCH_H

// The header provides the following macros to determine the host CPU architecture:
//
// _CCCL_ARCH(X86_64)
// _CCCL_ARCH(X86)
// _CCCL_ARCH(AARCH64)
// _CCCL_ARCH(ARM)
// _CCCL_ARCH(PPC64)

#if defined(__x86_64__) || defined(_M_X64)
#  define _CCCL_ARCH_X86_64_() 1
#else
#  define _CCCL_ARCH_X86_64_() 0
#endif

#if defined(__i386__) || defined(_M_IX86)
#  define _CCCL_ARCH_X86_() 1
#else
#  define _CCCL_ARCH_X86_() 0
#endif

#if defined(__aarch64__) || defined(_M_ARM64)
#  define _CCCL_ARCH_AARCH64_() 1
#else
#  define _CCCL_ARCH_AARCH64_() 0
#endif

#if defined(__arm__) || defined(_M_ARM)
#  define _CCCL_ARCH_ARM_() 1
#else
#  define _CCCL_ARCH_ARM_() 0
#endif

#if defined(__powerpc64__) || defined(__ppc64__)
#  define _CCCL_ARCH_PPC64_() 1
#else
#  define _CCCL_ARCH_PPC64_() 0
#endif

#define _CCCL_ARCH(...) _CCCL_ARCH_##__VA_ARGS__##_()

#endif // __CCCL_ARCH_H
