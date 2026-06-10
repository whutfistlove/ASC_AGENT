#include "asc/std/__numeric/abs_diff.h"
#include <iostream>

static int g_failures = 0;

template <typename T>
static void expect_eq(const char* expr, T got, T expected)
{
    bool ok = (got == expected);
    std::cout << "[host][abs_diff] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

int main()
{
    // Integer cases from CCCL test
    expect_eq("abs_diff(2, 5)",   asc::std::abs_diff(2, 5),   3);
    expect_eq("abs_diff(5, 2)",   asc::std::abs_diff(5, 2),   3);
    expect_eq("abs_diff(-4, 3)",  asc::std::abs_diff(-4, 3),  7);
    expect_eq("abs_diff(7, 7)",   asc::std::abs_diff(7, 7),   0);

    // Floating-point case from CCCL test
    expect_eq("abs_diff(2.5, 1.0)", asc::std::abs_diff(2.5, 1.0), 1.5);

    // Additional edge cases
    expect_eq("abs_diff(0, 0)",   asc::std::abs_diff(0, 0),   0);
    expect_eq("abs_diff(-3, -7)", asc::std::abs_diff(-3, -7), 4);
    expect_eq("abs_diff(-7, -3)", asc::std::abs_diff(-7, -3), 4);
    expect_eq("abs_diff(0, -5)",  asc::std::abs_diff(0, -5),  5);
    expect_eq("abs_diff(-5, 0)",  asc::std::abs_diff(-5, 0),  5);

    // Float additional
    expect_eq("abs_diff(-1.5, 2.5)", asc::std::abs_diff(-1.5, 2.5), 4.0);
    expect_eq("abs_diff(0.0, 0.0)",  asc::std::abs_diff(0.0, 0.0),  0.0);

    return g_failures == 0 ? 0 : 1;
}
