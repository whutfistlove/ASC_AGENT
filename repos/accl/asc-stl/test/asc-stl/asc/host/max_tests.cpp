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

int main()
{
    // Basic integer ordering
    expect_eq("max(1, 2)", asc::std::max(1, 2), 2);
    expect_eq("max(2, 1)", asc::std::max(2, 1), 2);
    expect_eq("max(-4, -9)", asc::std::max(-4, -9), -4);

    // Float values
    expect_eq("max(5.0f, 3.0f)", asc::std::max(5.0f, 3.0f), 5.0f);

    // Equal values: max returns the first argument (by const reference)
    {
        int a = 7;
        int b = 7;
        const int& r = asc::std::max(a, b);
        expect_eq("max(7,7) == 7", r, 7);
        // Verify it aliases the first input when equal
        expect_eq("&max(a,b) == &a when a==b", (&r == &a) ? 1 : 0, 1);
    }

    // Custom comparator (operator< wrapped in lambda)
    {
        auto comp = [](int x, int y) { return x < y; };
        expect_eq("max(10, 20, comp)", asc::std::max(10, 20, comp), 20);
        expect_eq("max(20, 10, comp)", asc::std::max(20, 10, comp), 20);
    }

    // Custom comparator with greater (reverses ordering -> returns the smaller)
    {
        auto greater_comp = [](int x, int y) { return x > y; };
        // comp(a,b) = (a > b); max(3,8) with greater: comp(3,8)=false -> returns a=3
        expect_eq("max(3, 8, greater_comp)", asc::std::max(3, 8, greater_comp), 3);
        // comp(8,3)=true -> returns b=3
        expect_eq("max(8, 3, greater_comp)", asc::std::max(8, 3, greater_comp), 3);
    }

    return g_failures == 0 ? 0 : 1;
}
