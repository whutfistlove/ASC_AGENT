#include "asc/std/algorithm.any_of.h"
#include <iostream>
#include <vector>

static int g_failures = 0;

static void expect_true(const char* expr, bool got)
{
    std::cout << "[host][any_of] " << expr << " = " << (got ? "true" : "false")
              << " (expected true) " << (got ? "OK" : "FAIL") << std::endl;
    if (!got) ++g_failures;
}

static void expect_false(const char* expr, bool got)
{
    std::cout << "[host][any_of] " << expr << " = " << (got ? "true" : "false")
              << " (expected false) " << (!got ? "OK" : "FAIL") << std::endl;
    if (got) ++g_failures;
}

int main()
{
    // Test 1: Empty range — any_of should return false
    {
        std::vector<int> v;
        expect_false("any_of(empty, >0)", asc::std::any_of(v.begin(), v.end(), [](int x) { return x > 0; }));
    }

    // Test 2: All elements satisfy predicate — should return true
    {
        int arr[] = {2, 4, 6, 8};
        expect_true("any_of(all_even, even)", asc::std::any_of(arr, arr + 4, [](int x) { return x % 2 == 0; }));
    }

    // Test 3: No elements satisfy predicate — should return false
    {
        int arr[] = {1, 3, 5, 7};
        expect_false("any_of(all_odd, even)", asc::std::any_of(arr, arr + 4, [](int x) { return x % 2 == 0; }));
    }

    // Test 4: Some elements satisfy predicate — should return true
    {
        int arr[] = {1, 2, 3, 4};
        expect_true("any_of(mixed, even)", asc::std::any_of(arr, arr + 4, [](int x) { return x % 2 == 0; }));
    }

    // Test 5: Single element satisfying — should return true
    {
        int arr[] = {5};
        expect_true("any_of({5}, >0)", asc::std::any_of(arr, arr + 1, [](int x) { return x > 0; }));
    }

    // Test 6: Single element not satisfying — should return false
    {
        int arr[] = {-3};
        expect_false("any_of({-3}, >0)", asc::std::any_of(arr, arr + 1, [](int x) { return x > 0; }));
    }

    // Test 7: First element satisfies — should return true (early exit)
    {
        int arr[] = {10, 1, 1, 1};
        expect_true("any_of(first_is_10, ==10)", asc::std::any_of(arr, arr + 4, [](int x) { return x == 10; }));
    }

    // Test 8: Last element satisfies — should return true
    {
        int arr[] = {1, 1, 1, 42};
        expect_true("any_of(last_is_42, ==42)", asc::std::any_of(arr, arr + 4, [](int x) { return x == 42; }));
    }

    // Test 9: Float range with predicate
    {
        float arr[] = {0.0f, -1.0f, -2.0f};
        expect_false("any_of(negative_floats, >0)", asc::std::any_of(arr, arr + 3, [](float x) { return x > 0.0f; }));
    }

    // Test 10: Float range with some positive
    {
        float arr[] = {-1.0f, 0.0f, 3.5f};
        expect_true("any_of(mixed_floats, >0)", asc::std::any_of(arr, arr + 3, [](float x) { return x > 0.0f; }));
    }

    // Test 11: Custom predicate — check for zero
    {
        int arr[] = {3, 7, 0, 9};
        expect_true("any_of(has_zero, ==0)", asc::std::any_of(arr, arr + 4, [](int x) { return x == 0; }));
    }

    // Test 12: Range with all zeros — predicate checks non-zero
    {
        int arr[] = {0, 0, 0};
        expect_false("any_of(all_zero, !=0)", asc::std::any_of(arr, arr + 3, [](int x) { return x != 0; }));
    }

    return g_failures == 0 ? 0 : 1;
}
