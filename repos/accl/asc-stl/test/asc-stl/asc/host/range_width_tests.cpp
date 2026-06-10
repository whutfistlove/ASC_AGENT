#include "asc/std/__numeric/range_width.h"
#include <iostream>

static int g_failures = 0;

template <typename T>
static void expect_eq(const char* expr, T got, T expected)
{
    bool ok = (got == expected);
    std::cout << "[host][range_width] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

int main()
{
    // Integer cases from CCCL upstream test
    expect_eq("range_width(1, 2, 3)", asc::std::range_width(1, 2, 3), 2);
    expect_eq("range_width(3, 1, 2)", asc::std::range_width(3, 1, 2), 2);
    expect_eq("range_width(5, 5, 5)", asc::std::range_width(5, 5, 5), 0);
    expect_eq("range_width(-4, 9, 1)", asc::std::range_width(-4, 9, 1), 13);
    expect_eq("range_width(2, 2, 8)", asc::std::range_width(2, 2, 8), 6);

    // Additional integer coverage
    expect_eq("range_width(7, 7, 7)", asc::std::range_width(7, 7, 7), 0);
    expect_eq("range_width(-10, -5, -1)", asc::std::range_width(-10, -5, -1), 9);
    expect_eq("range_width(4, 4, 10)", asc::std::range_width(4, 4, 10), 6);
    expect_eq("range_width(10, 4, 4)", asc::std::range_width(10, 4, 4), 6);

    // Float cases
    expect_eq("range_width(1.0f, 2.0f, 3.0f)", asc::std::range_width(1.0f, 2.0f, 3.0f), 2.0f);
    expect_eq("range_width(-1.5f, 0.5f, 3.5f)", asc::std::range_width(-1.5f, 0.5f, 3.5f), 5.0f);
    expect_eq("range_width(0.0f, 0.0f, 0.0f)", asc::std::range_width(0.0f, 0.0f, 0.0f), 0.0f);

    return g_failures == 0 ? 0 : 1;
}
