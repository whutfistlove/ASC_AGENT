#include "asc/std/cfloat"
#include <iostream>
#include <type_traits>

static int g_failures = 0;

static void expect_eq_int(const char* expr, int got, int expected)
{
    bool ok = (got == expected);
    std::cout << "[host][cfloat] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

static void expect_eq_float(const char* expr, float got, float expected)
{
    bool ok = (got == expected);
    std::cout << "[host][cfloat] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

static void expect_eq_double(const char* expr, double got, double expected)
{
    bool ok = (got == expected);
    std::cout << "[host][cfloat] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

static void expect_true(const char* expr, bool cond)
{
    std::cout << "[host][cfloat] " << expr << " = " << (cond ? "true" : "false")
              << " (expected true) " << (cond ? "OK" : "FAIL") << std::endl;
    if (!cond) ++g_failures;
}

int main()
{
    // FLT_RADIX
    expect_eq_int("FLT_RADIX", FLT_RADIX, 2);

    // FLT_EVAL_METHOD
    {
        [[maybe_unused]] constexpr auto flt_eval_method = FLT_EVAL_METHOD;
        (void)flt_eval_method;
        std::cout << "[host][cfloat] FLT_EVAL_METHOD = " << FLT_EVAL_METHOD << " (exists) OK" << std::endl;
    }

    // FLT_DECIMAL_DIG
#ifdef FLT_DECIMAL_DIG
    expect_eq_int("FLT_DECIMAL_DIG", FLT_DECIMAL_DIG, 9);
#else
    std::cout << "[host][cfloat] FLT_DECIMAL_DIG not defined (SKIP)" << std::endl;
#endif

    // FLT_MIN
    expect_eq_float("FLT_MIN", FLT_MIN, 1.17549435082228750796873653722224568e-38f);
    expect_true("decltype(FLT_MIN) is float", std::is_same_v<decltype(FLT_MIN), float>);

    // FLT_TRUE_MIN
#ifdef FLT_TRUE_MIN
    expect_eq_float("FLT_TRUE_MIN", FLT_TRUE_MIN, 1.40129846432481707092372958328991613e-45f);
    expect_true("decltype(FLT_TRUE_MIN) is float", std::is_same_v<decltype(FLT_TRUE_MIN), float>);
#else
    std::cout << "[host][cfloat] FLT_TRUE_MIN not defined (SKIP)" << std::endl;
#endif

    // FLT_MAX
    expect_eq_float("FLT_MAX", FLT_MAX, 3.40282346638528859811704183484516925e+38f);
    expect_true("decltype(FLT_MAX) is float", std::is_same_v<decltype(FLT_MAX), float>);

    // FLT_EPSILON
    expect_eq_float("FLT_EPSILON", FLT_EPSILON, 1.19209289550781250000000000000000000e-7f);
    expect_true("decltype(FLT_EPSILON) is float", std::is_same_v<decltype(FLT_EPSILON), float>);

    // FLT_DIG
    expect_eq_int("FLT_DIG", FLT_DIG, 6);

    // FLT_MANT_DIG
    expect_eq_int("FLT_MANT_DIG", FLT_MANT_DIG, 24);

    // FLT_MIN_EXP
    expect_eq_int("FLT_MIN_EXP", FLT_MIN_EXP, -125);

    // FLT_MIN_10_EXP
    expect_eq_int("FLT_MIN_10_EXP", FLT_MIN_10_EXP, -37);

    // FLT_MAX_EXP
    expect_eq_int("FLT_MAX_EXP", FLT_MAX_EXP, 128);

    // FLT_MAX_10_EXP
    expect_eq_int("FLT_MAX_10_EXP", FLT_MAX_10_EXP, 38);

    // FLT_HAS_SUBNORM
#ifdef FLT_HAS_SUBNORM
    expect_eq_int("FLT_HAS_SUBNORM", FLT_HAS_SUBNORM, 1);
#else
    std::cout << "[host][cfloat] FLT_HAS_SUBNORM not defined (SKIP)" << std::endl;
#endif

    // DBL_DECIMAL_DIG
#ifdef DBL_DECIMAL_DIG
    expect_eq_int("DBL_DECIMAL_DIG", DBL_DECIMAL_DIG, 17);
#else
    std::cout << "[host][cfloat] DBL_DECIMAL_DIG not defined (SKIP)" << std::endl;
#endif

    // DBL_MIN
    expect_eq_double("DBL_MIN", DBL_MIN, 2.22507385850720138309023271733240406e-308);
    expect_true("decltype(DBL_MIN) is double", std::is_same_v<decltype(DBL_MIN), double>);

    // DBL_TRUE_MIN
#ifdef DBL_TRUE_MIN
    expect_eq_double("DBL_TRUE_MIN", DBL_TRUE_MIN, 4.94065645841246544176568792868221372e-324);
    expect_true("decltype(DBL_TRUE_MIN) is double", std::is_same_v<decltype(DBL_TRUE_MIN), double>);
#else
    std::cout << "[host][cfloat] DBL_TRUE_MIN not defined (SKIP)" << std::endl;
#endif

    // DBL_MAX
    expect_eq_double("DBL_MAX", DBL_MAX, 1.79769313486231570814527423731704357e+308);
    expect_true("decltype(DBL_MAX) is double", std::is_same_v<decltype(DBL_MAX), double>);

    // DBL_EPSILON
    expect_eq_double("DBL_EPSILON", DBL_EPSILON, 2.22044604925031308084726333618164062e-16);
    expect_true("decltype(DBL_EPSILON) is double", std::is_same_v<decltype(DBL_EPSILON), double>);

    // DBL_DIG
    expect_eq_int("DBL_DIG", DBL_DIG, 15);

    // DBL_MANT_DIG
    expect_eq_int("DBL_MANT_DIG", DBL_MANT_DIG, 53);

    // DBL_MIN_EXP
    expect_eq_int("DBL_MIN_EXP", DBL_MIN_EXP, -1021);

    // DBL_MIN_10_EXP
    expect_eq_int("DBL_MIN_10_EXP", DBL_MIN_10_EXP, -307);

    // DBL_MAX_EXP
    expect_eq_int("DBL_MAX_EXP", DBL_MAX_EXP, 1024);

    // DBL_MAX_10_EXP
    expect_eq_int("DBL_MAX_10_EXP", DBL_MAX_10_EXP, 308);

    // DBL_HAS_SUBNORM
#ifdef DBL_HAS_SUBNORM
    expect_eq_int("DBL_HAS_SUBNORM", DBL_HAS_SUBNORM, 1);
#else
    std::cout << "[host][cfloat] DBL_HAS_SUBNORM not defined (SKIP)" << std::endl;
#endif

    // DECIMAL_DIG (if defined)
#ifdef DECIMAL_DIG
    {
        constexpr auto decimal_dig = DECIMAL_DIG;
        std::cout << "[host][cfloat] DECIMAL_DIG = " << decimal_dig << " (exists) OK" << std::endl;
    }
#else
    std::cout << "[host][cfloat] DECIMAL_DIG not defined (SKIP)" << std::endl;
#endif

    // FLT_ROUNDS (host-only per CCCL test)
    {
        const auto flt_rounds = FLT_ROUNDS;
        std::cout << "[host][cfloat] FLT_ROUNDS = " << flt_rounds << " (exists) OK" << std::endl;
    }

    return g_failures == 0 ? 0 : 1;
}
