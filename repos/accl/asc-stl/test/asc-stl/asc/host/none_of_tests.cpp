#include "asc/std/__algorithm/none_of.h"
#include <iostream>

static int g_failures = 0;

static void expect_eq(const char* expr, bool got, bool expected)
{
    bool ok = (got == expected);
    std::cout << "[host][none_of] " << expr << " = " << (got ? "true" : "false")
              << " (expected " << (expected ? "true" : "false") << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

int main()
{
    auto is_even = [](const int& i) { return i % 2 == 0; };

    // All even → none_of(is_even) = false (some satisfy predicate)
    {
        int ia[] = {2, 4, 6, 8};
        expect_eq("none_of({2,4,6,8}, is_even)",
                  asc::std::none_of(ia, ia + 4, is_even), false);
    }

    // Mixed even/odd → none_of(is_even) = false
    {
        int ia[] = {2, 4, 5, 8};
        expect_eq("none_of({2,4,5,8}, is_even)",
                  asc::std::none_of(ia, ia + 4, is_even), false);
    }

    // All odd → none_of(is_even) = true
    {
        int ia[] = {1, 3, 5, 7};
        expect_eq("none_of({1,3,5,7}, is_even)",
                  asc::std::none_of(ia, ia + 4, is_even), true);
    }

    // Empty range → none_of = true
    {
        int ia[] = {2, 4, 6, 8};
        expect_eq("none_of(empty_range, is_even)",
                  asc::std::none_of(ia, ia, is_even), true);
    }

    // Single element: odd → true
    {
        int x = 3;
        expect_eq("none_of({3}, is_even)",
                  asc::std::none_of(&x, &x + 1, is_even), true);
    }

    // Single element: even → false
    {
        int x = 4;
        expect_eq("none_of({4}, is_even)",
                  asc::std::none_of(&x, &x + 1, is_even), false);
    }

    // Constexpr test equivalent: mixed with one even, and all odd
    {
        int ia[] = {1, 3, 6, 7};  // 6 is even → none_of(is_even) = false
        int ib[] = {1, 3, 5, 7};  // all odd → none_of(is_even) = true
        expect_eq("none_of({1,3,6,7}, is_even)",
                  asc::std::none_of(ia, ia + 4, is_even), false);
        expect_eq("none_of({1,3,5,7}, is_even)",
                  asc::std::none_of(ib, ib + 4, is_even), true);
    }

    return g_failures == 0 ? 0 : 1;
}
