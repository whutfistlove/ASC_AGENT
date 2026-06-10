#include "asc/std/__algorithm/max.h"
#include <iostream>

static int g_failures = 0;

template <typename T>
static void expect_eq(const char* expr, T got, T expected)
{
    bool ok = (got == expected);
    std::cout << "[host][max] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

static void expect_true(const char* expr, bool cond)
{
    std::cout << "[host][max] " << expr << " = " << (cond ? "true" : "false")
              << " (expected true) " << (cond ? "OK" : "FAIL") << std::endl;
    if (!cond) ++g_failures;
}

int main()
{
    expect_eq("max(1, 2)", asc::std::max(1, 2), 2);
    expect_eq("max(2, 1)", asc::std::max(2, 1), 2);
    expect_eq("max(5.0f, 3.0f)", asc::std::max(5.0f, 3.0f), 5.0f);
    expect_eq("max(-4, -9)", asc::std::max(-4, -9), -4);

    {
        int a = 7;
        int b = 7;
        expect_true("&max(a, b) == &a (equal values)", &asc::std::max(a, b) == &a);
    }

    {
        auto comp = [](int x, int y) { return x < y; };
        expect_eq("max(10, 20, comp)", asc::std::max(10, 20, comp), 20);
        expect_eq("max(20, 10, comp)", asc::std::max(20, 10, comp), 20);
    }

    {
        auto greater = [](int x, int y) { return x > y; };
        expect_eq("max(10, 20, greater)", asc::std::max(10, 20, greater), 10);
        expect_eq("max(20, 10, greater)", asc::std::max(20, 10, greater), 10);
    }

    return g_failures == 0 ? 0 : 1;
}
