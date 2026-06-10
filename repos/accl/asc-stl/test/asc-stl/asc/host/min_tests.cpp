#include "asc/std/__algorithm/min.h"
#include <iostream>

static int g_failures = 0;

template <typename T>
static void expect_eq(const char* expr, T got, T expected)
{
    bool ok = (got == expected);
    std::cout << "[host][min] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

int main()
{
    // Basic ordering on integers
    expect_eq("min(1, 2)", asc::std::min(1, 2), 1);
    expect_eq("min(2, 1)", asc::std::min(2, 1), 1);
    expect_eq("min(-4, -9)", asc::std::min(-4, -9), -9);

    // Float values
    expect_eq("min(5.0f, 3.0f)", asc::std::min(5.0f, 3.0f), 3.0f);
    expect_eq("min(-2.5f, -7.1f)", asc::std::min(-2.5f, -7.1f), -7.1f);

    // Equal values: the first argument is returned (by reference)
    {
        int a = 7;
        int b = 7;
        const int& result = asc::std::min(a, b);
        expect_eq("&min(a,b) == &a (equal ints)", (&result == &a) ? 1 : 0, 1);
    }

    // Custom comparator (plain operator< wrapped in a lambda)
    {
        auto comp = [](int x, int y) { return x < y; };
        expect_eq("min(10, 20, comp)", asc::std::min(10, 20, comp), 10);
        expect_eq("min(20, 10, comp)", asc::std::min(20, 10, comp), 10);
        expect_eq("min(5, 5, comp)", asc::std::min(5, 5, comp), 5);
    }

    return g_failures == 0 ? 0 : 1;
}
