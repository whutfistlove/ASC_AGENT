#include "asc/std/__algorithm/median3.h"
#include <iostream>

static int g_failures = 0;

template <typename T>
static void expect_eq(const char* expr, T got, T expected)
{
    bool ok = (got == expected);
    std::cout << "[host][median3] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

int main()
{
    // Already sorted
    expect_eq("median3(1,2,3)", asc::std::median3(1, 2, 3), 2);
    // Fully reversed
    expect_eq("median3(3,2,1)", asc::std::median3(3, 2, 1), 2);
    // Middle first
    expect_eq("median3(2,3,1)", asc::std::median3(2, 3, 1), 2);
    // Another permutation
    expect_eq("median3(3,1,2)", asc::std::median3(3, 1, 2), 2);

    // Duplicates — the repeated value is the median
    expect_eq("median3(5,5,1)", asc::std::median3(5, 5, 1), 5);
    expect_eq("median3(1,7,7)", asc::std::median3(1, 7, 7), 7);

    // Negative values
    expect_eq("median3(-3,0,3)", asc::std::median3(-3, 0, 3), 0);

    // Floating point
    expect_eq("median3(2.5f,1.0f,2.0f)", asc::std::median3(2.5f, 1.0f, 2.0f), 2.0f);

    return g_failures == 0 ? 0 : 1;
}
