#include "asc/std/algorithm.all_of.h"
#include <iostream>
#include <vector>

static int g_failures = 0;

static void expect_true(const char* expr, bool got)
{
    std::cout << "[host][all_of] " << expr << " = " << (got ? "true" : "false")
              << " (expected true) " << (got ? "OK" : "FAIL") << std::endl;
    if (!got) ++g_failures;
}

static void expect_false(const char* expr, bool got)
{
    std::cout << "[host][all_of] " << expr << " = " << (got ? "true" : "false")
              << " (expected false) " << (got ? "FAIL" : "OK") << std::endl;
    if (got) ++g_failures;
}

int main()
{
    // Test 1: All elements satisfy predicate -> true
    {
        int arr[] = {2, 4, 6, 8, 10};
        auto is_even = [](int x) { return x % 2 == 0; };
        expect_true("all_of(all even)", asc::std::all_of(arr, arr + 5, is_even));
    }

    // Test 2: Some elements don't satisfy -> false
    {
        int arr[] = {2, 3, 6, 8, 10};
        auto is_even = [](int x) { return x % 2 == 0; };
        expect_false("all_of(one odd)", asc::std::all_of(arr, arr + 5, is_even));
    }

    // Test 3: No elements satisfy -> false
    {
        int arr[] = {1, 3, 5, 7, 9};
        auto is_even = [](int x) { return x % 2 == 0; };
        expect_false("all_of(all odd)", asc::std::all_of(arr, arr + 5, is_even));
    }

    // Test 4: Empty range -> true (standard behavior)
    {
        int arr[] = {1, 2, 3};
        auto is_even = [](int x) { return x % 2 == 0; };
        expect_true("all_of(empty range)", asc::std::all_of(arr, arr, is_even));
    }

    // Test 5: Single element that satisfies -> true
    {
        int arr[] = {4};
        auto is_even = [](int x) { return x % 2 == 0; };
        expect_true("all_of(single even)", asc::std::all_of(arr, arr + 1, is_even));
    }

    // Test 6: Single element that doesn't satisfy -> false
    {
        int arr[] = {3};
        auto is_even = [](int x) { return x % 2 == 0; };
        expect_false("all_of(single odd)", asc::std::all_of(arr, arr + 1, is_even));
    }

    // Test 7: With vector and positive predicate
    {
        std::vector<int> v = {5, 10, 15, 20};
        auto is_positive = [](int x) { return x > 0; };
        expect_true("all_of(all positive)", asc::std::all_of(v.begin(), v.end(), is_positive));
    }

    // Test 8: With vector, some negative
    {
        std::vector<int> v = {5, -3, 15, 20};
        auto is_positive = [](int x) { return x > 0; };
        expect_false("all_of(one negative)", asc::std::all_of(v.begin(), v.end(), is_positive));
    }

    // Test 9: Float range with predicate
    {
        float arr[] = {1.5f, 2.5f, 3.5f};
        auto gt_one = [](float x) { return x > 1.0f; };
        expect_true("all_of(floats > 1.0)", asc::std::all_of(arr, arr + 3, gt_one));
    }

    // Test 10: First element fails (short-circuit)
    {
        int arr[] = {1, 2, 4, 6};
        auto is_even = [](int x) { return x % 2 == 0; };
        expect_false("all_of(first fails)", asc::std::all_of(arr, arr + 4, is_even));
    }

    // Test 11: Last element fails
    {
        int arr[] = {2, 4, 6, 7};
        auto is_even = [](int x) { return x % 2 == 0; };
        expect_false("all_of(last fails)", asc::std::all_of(arr, arr + 4, is_even));
    }

    return g_failures == 0 ? 0 : 1;
}
