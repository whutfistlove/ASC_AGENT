#include "asc/std/__algorithm/all_of.h"
#include <iostream>

static int g_failures = 0;

static void expect_eq(const char* expr, bool got, bool expected)
{
    bool ok = (got == expected);
    std::cout << "[host][all_of] " << expr << " = " << (got ? "true" : "false")
              << " (expected " << (expected ? "true" : "false") << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

int main()
{
    // Test: all elements satisfy predicate -> true
    {
        int ia[] = {2, 4, 6, 8};
        auto is_even = [](const int& i) { return i % 2 == 0; };
        expect_eq("all_of({2,4,6,8}, is_even)",
                  asc::std::all_of(ia, ia + 4, is_even), true);
    }

    // Test: not all elements satisfy predicate -> false
    {
        int ia[] = {2, 4, 5, 8};
        auto is_even = [](const int& i) { return i % 2 == 0; };
        expect_eq("all_of({2,4,5,8}, is_even)",
                  asc::std::all_of(ia, ia + 4, is_even), false);
    }

    // Test: empty range -> true
    {
        int ia[] = {1, 2, 3};
        auto is_even = [](const int& i) { return i % 2 == 0; };
        expect_eq("all_of(empty range, is_even)",
                  asc::std::all_of(ia, ia, is_even), true);
    }

    // Test: single element satisfying predicate -> true
    {
        int ia[] = {4};
        auto is_even = [](const int& i) { return i % 2 == 0; };
        expect_eq("all_of({4}, is_even)",
                  asc::std::all_of(ia, ia + 1, is_even), true);
    }

    // Test: single element not satisfying predicate -> false
    {
        int ia[] = {3};
        auto is_even = [](const int& i) { return i % 2 == 0; };
        expect_eq("all_of({3}, is_even)",
                  asc::std::all_of(ia, ia + 1, is_even), false);
    }

    // Test: with float and positive predicate
    {
        float fa[] = {1.0f, 2.5f, 3.7f};
        auto is_positive = [](const float& f) { return f > 0.0f; };
        expect_eq("all_of({1.0,2.5,3.7}, is_positive)",
                  asc::std::all_of(fa, fa + 3, is_positive), true);
    }

    // Test: with float, not all positive
    {
        float fa[] = {1.0f, -2.5f, 3.7f};
        auto is_positive = [](const float& f) { return f > 0.0f; };
        expect_eq("all_of({1.0,-2.5,3.7}, is_positive)",
                  asc::std::all_of(fa, fa + 3, is_positive), false);
    }

    return g_failures == 0 ? 0 : 1;
}
