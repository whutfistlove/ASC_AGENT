#ifndef ASC_STL_INCLUDE_ASC_STD___HOST_STDLIB_MATH_H_
#define ASC_STL_INCLUDE_ASC_STD___HOST_STDLIB_MATH_H_

#include "asc/std/__config"

#if defined(__CCE__)
#define ASC_DEVICE_CODE
#else
#include <math.h>

// Standard C++ library comes with it's own <math.h> C++ compatible header. However, if the include paths are jumbled,
// it might happen that the original C <math.h> is found first. This is a problem because C headers define many of the
// math functions as macros which would change our definitions. So, we check whether any of the functions are defined
// as a macro to distinguish the C++ compatibility header from the C header.
#if defined(fabs) || defined(fmod) || defined(remainder) || defined(remquo) || defined(fma) || defined(fmax)      \
    || defined(fmin) || defined(fdim) || defined(exp) || defined(exp2) || defined(expm1) || defined(log)            \
    || defined(log10) || defined(log2) || defined(log1p) || defined(pow) || defined(sqrt) || defined(cbrt)          \
    || defined(hypot) || defined(sin) || defined(cos) || defined(tan) || defined(asin) || defined(acos)             \
    || defined(atan) || defined(atan2) || defined(sinh) || defined(cosh) || defined(tanh) || defined(asinh)         \
    || defined(acosh) || defined(atanh) || defined(erf) || defined(erfc) || defined(tgamma) || defined(lgamma)      \
    || defined(ceil) || defined(floor) || defined(trunc) || defined(round) || defined(lround) || defined(llround)   \
    || defined(nearbyint) || defined(rint) || defined(lrint) || defined(llrint) || defined(frexp) || defined(ldexp) \
    || defined(scalbn) || defined(scalbln) || defined(ilogb) || defined(logb) || defined(nextafter)                 \
    || defined(nexttoward) || defined(copysign) || defined(fpclassify) || defined(isfinite) || defined(isinf)       \
    || defined(isnan) || defined(isnormal) || defined(signbit) || defined(isgreater) || defined(isgreaterequal)     \
    || defined(isless) || defined(islessequal) || defined(islessgreater) || defined(isunordered)
#    error \
      "ASC-STL requires the C++ compatibility <math.h> header, not the C <math.h> header. Please, check your include paths."
#endif // math functions defined as macros

#endif // __CCE__

// [MIGRATION NOTE] The original CCCL header conditionally included the host's
// <math.h> via _CCCL_HOSTED() and checked that the C++ compatibility version
// (not the C version) was found. ASC-STL does not have _CCCL_HOSTED, so we
// include <math.h> directly on the host side. On the device side (__CCE__),
// <math.h> is not available. The C-vs-C++ macro detection check is preserved
// on the host path to catch misconfigured include paths.

#endif // ASC_STL_INCLUDE_ASC_STD___HOST_STDLIB_MATH_H_
