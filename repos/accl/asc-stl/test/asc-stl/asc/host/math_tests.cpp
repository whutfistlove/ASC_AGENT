#include "asc/std/__host_stdlib/math.h"
#include <iostream>
#include <cmath>

static int g_failures = 0;

static void expect_eq_d(const char* expr, double got, double expected)
{
    bool ok = (got == expected);
    std::cout << "[host][math] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

static void expect_near(const char* expr, double got, double expected, double tol = 1e-9)
{
    bool ok = (got == expected) || (__builtin_fabs(got - expected) < tol);
    std::cout << "[host][math] " << expr << " = " << got
              << " (expected ~" << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

static void expect_eq_i(const char* expr, int got, int expected)
{
    bool ok = (got == expected);
    std::cout << "[host][math] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

int main()
{
    // This header is a host-only shim: it includes the system <math.h>
    // on the host path, and defines ASC_DEVICE_CODE on the device path.
    // No asc::std:: namespaced functions are provided — it merely makes
    // the standard C math library available. We test representative
    // functions from <math.h> and verify the C++ compatibility header
    // was included (not the C macro version).

    // --- fabs ---
    expect_eq_d("fabs(-3.0)", fabs(-3.0), 3.0);
    expect_eq_d("fabs(0.0)",  fabs(0.0),  0.0);
    expect_eq_d("fabs(5.5)",  fabs(5.5),  5.5);

    // --- sqrt ---
    expect_eq_d("sqrt(4.0)",  sqrt(4.0),  2.0);
    expect_eq_d("sqrt(0.0)",  sqrt(0.0),  0.0);
    expect_near("sqrt(2.0)",  sqrt(2.0),  1.4142135623730951);

    // --- ceil / floor / trunc / round ---
    expect_eq_d("ceil(1.2)",   ceil(1.2),   2.0);
    expect_eq_d("ceil(-1.2)",  ceil(-1.2), -1.0);
    expect_eq_d("floor(1.8)",  floor(1.8),  1.0);
    expect_eq_d("floor(-1.8)", floor(-1.8), -2.0);
    expect_eq_d("trunc(1.9)",  trunc(1.9),  1.0);
    expect_eq_d("trunc(-1.9)", trunc(-1.9), -1.0);
    expect_eq_d("round(1.5)",  round(1.5),  2.0);
    expect_eq_d("round(2.5)",  round(2.5),  3.0);
    expect_eq_d("round(-1.5)", round(-1.5), -2.0);

    // --- fmin / fmax ---
    expect_eq_d("fmin(1.0, 2.0)",  fmin(1.0, 2.0),  1.0);
    expect_eq_d("fmax(1.0, 2.0)",  fmax(1.0, 2.0),  2.0);
    expect_eq_d("fmin(-5.0, 3.0)", fmin(-5.0, 3.0), -5.0);
    expect_eq_d("fmax(-5.0, 3.0)", fmax(-5.0, 3.0),  3.0);

    // --- pow ---
    expect_eq_d("pow(2.0, 3.0)", pow(2.0, 3.0), 8.0);
    expect_eq_d("pow(3.0, 2.0)", pow(3.0, 2.0), 9.0);

    // --- exp / log ---
    expect_near("exp(1.0)",       exp(1.0),       2.7182818284590452);
    expect_near("log(exp(1.0))",  log(exp(1.0)),  1.0);
    expect_eq_d("log10(100.0)",   log10(100.0),   2.0);

    // --- sin / cos / tan (basic known values) ---
    expect_near("sin(0.0)", sin(0.0), 0.0);
    expect_eq_d("cos(0.0)",  cos(0.0), 1.0);
    expect_near("tan(0.0)", tan(0.0), 0.0);

    // --- copysign ---
    expect_eq_d("copysign(3.0, -1.0)",  copysign(3.0, -1.0),  -3.0);
    expect_eq_d("copysign(-3.0, 1.0)",  copysign(-3.0, 1.0),   3.0);

    // --- fmod ---
    expect_near("fmod(5.3, 2.0)", fmod(5.3, 2.0), 1.3);

    // --- classification: isfinite / isnan / isinf ---
    expect_eq_i("isfinite(1.0)", isfinite(1.0), 1);
    expect_eq_i("isnan(0.0)",    isnan(0.0),    0);

    // --- Verify C++ compatibility <math.h> was included (not C macro version) ---
    // In the C <math.h>, fabs etc. are macros, so you cannot take their address.
    // In the C++ compatibility <math.h>, they are real functions.
    {
        double (*fp)(double) = &fabs;
        (void)fp;  // suppress unused warning
        std::cout << "[host][math] &fabs is a valid function pointer (C++ <math.h>) OK" << std::endl;
    }

    // --- Verify ASC_DEVICE_CODE is not defined on host ---
#if defined(ASC_DEVICE_CODE)
    std::cout << "[host][math] ASC_DEVICE_CODE is defined (unexpected on host) FAIL" << std::endl;
    ++g_failures;
#else
    std::cout << "[host][math] ASC_DEVICE_CODE is not defined (correct for host) OK" << std::endl;
#endif

    return g_failures == 0 ? 0 : 1;
}
