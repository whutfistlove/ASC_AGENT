// ACCL-side host test for min, migrated from the CCCL min test.
//
// min is a binary value-returning op (returns the smaller of a, b).
// The test compares the result to an INDEPENDENT expected value,
// never to ascend::std::min again.
#include "ascend/std/__algorithm/min.h"
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

static void expect_true(const char* expr, bool cond)
{
    std::cout << "[host][min] " << expr << " = " << (cond ? "true" : "false")
              << " (expected true) " << (cond ? "OK" : "FAIL") << std::endl;
    if (!cond) ++g_failures;
}

int main()
{
    // Basic ordering on integers and floats
    expect_eq("min(1, 2)", ascend::std::min(1, 2), 1);
    expect_eq("min(2, 1)", ascend::std::min(2, 1), 1);
    expect_eq("min(5.0f, 3.0f)", ascend::std::min(5.0f, 3.0f), 3.0f);
    expect_eq("min(-4, -9)", ascend::std::min(-4, -9), -9);

    // Equal values: the first argument is returned (by reference)
    {
        int a = 7;
        int b = 7;
        expect_true("&min(a, b) == &a (equal values)", &ascend::std::min(a, b) == &a);
    }

    // Custom comparator (plain operator< wrapped in a lambda)
    {
        auto comp = [](int x, int y) { return x < y; };
        expect_eq("min(10, 20, comp)", ascend::std::min(10, 20, comp), 10);
        expect_eq("min(20, 10, comp)", ascend::std::min(20, 10, comp), 10);
    }

    return g_failures == 0 ? 0 : 1;
}
