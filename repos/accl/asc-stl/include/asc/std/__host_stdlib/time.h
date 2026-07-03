#ifndef ASC_STL_INCLUDE_ASC_STD___HOST_STDLIB_TIME_H_
#define ASC_STL_INCLUDE_ASC_STD___HOST_STDLIB_TIME_H_

#include "asc/std/__config"

#if defined(__CCE__)
#define ASC_DEVICE_CODE
#else
#include <time.h>

// Standard C++ library comes with it's own <time.h> C++ compatible header. However, if the include paths are jumbled,
// it might happen that the original C <time.h> is found first. This is a problem because C headers define many of the
// time functions as macros which would change our definitions. So, we check whether any of the functions are defined
// as a macro to distinguish the C++ compatibility header from the C header.
#if defined(clock) || defined(difftime) || defined(mktime) || defined(time) || defined(asctime) || defined(ctime) \
    || defined(gmtime) || defined(localtime) || defined(strftime)
#    error \
      "ASC-STL requires the C++ compatibility <time.h> header, not the C <time.h> header. Please, check your include paths."
#endif // time functions defined as macros

#endif // __CCE__

// [MIGRATION NOTE] The original CCCL header conditionally included the host's
// <time.h> via _CCCL_HOSTED() and checked that the C++ compatibility version
// (not the C version) was found. ASC-STL does not have _CCCL_HOSTED, so we
// include <time.h> directly on the host side. On the device side (__CCE__),
// <time.h> is not available. The C-vs-C++ macro detection check is preserved
// on the host path to catch misconfigured include paths.

#endif // ASC_STL_INCLUDE_ASC_STD___HOST_STDLIB_TIME_H_
