#include "asc/std/__algorithm/replace_if.h"
#include <iostream>
#include <vector>

static int g_failures = 0;

template <typename T>
static void expect_eq(const char* expr, T got, T expected)
{
    bool ok = (got == expected);
    std::cout << "[host][replace_if] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

int main()
{
    // Basic test: replace negative values with 0
    {
        int arr[] = {3, -1, 4, -5, 9, -2};
        auto is_negative = [](int x) { return x < 0; };
        asc::std::replace_if(arr, arr + 6, is_negative, 0);
        expect_eq("arr[0] after replace_if (was 3)", arr[0], 3);
        expect_eq("arr[1] after replace_if (was -1)", arr[1], 0);
        expect_eq("arr[2] after replace_if (was 4)", arr[2], 4);
        expect_eq("arr[3] after replace_if (was -5)", arr[3], 0);
        expect_eq("arr[4] after replace_if (was 9)", arr[4], 9);
        expect_eq("arr[5] after replace_if (was -2)", arr[5], 0);
    }

    // No matches: nothing should change
    {
        int arr[] = {1, 2, 3};
        auto is_negative = [](int x) { return x < 0; };
        asc::std::replace_if(arr, arr + 3, is_negative, 99);
        expect_eq("no-match arr[0]", arr[0], 1);
        expect_eq("no-match arr[1]", arr[1], 2);
        expect_eq("no-match arr[2]", arr[2], 3);
    }

    // All match: all should be replaced
    {
        int arr[] = {2, 4, 6};
        auto is_even = [](int x) { return x % 2 == 0; };
        asc::std::replace_if(arr, arr + 3, is_even, -1);
        expect_eq("all-match arr[0]", arr[0], -1);
        expect_eq("all-match arr[1]", arr[1], -1);
        expect_eq("all-match arr[2]", arr[2], -1);
    }

    // Empty range: should not crash or modify anything
    {
        int arr[] = {42};
        auto pred = [](int) { return true; };
        asc::std::replace_if(arr, arr, pred, 0);
        expect_eq("empty-range arr[0]", arr[0], 42);
    }

    // Single element, matches
    {
        int arr[] = {5};
        auto is_five = [](int x) { return x == 5; };
        asc::std::replace_if(arr, arr + 1, is_five, 10);
        expect_eq("single-match arr[0]", arr[0], 10);
    }

    // Single element, no match
    {
        int arr[] = {5};
        auto is_three = [](int x) { return x == 3; };
        asc::std::replace_if(arr, arr + 1, is_three, 10);
        expect_eq("single-nomatch arr[0]", arr[0], 5);
    }

    // With float values
    {
        float arr[] = {1.5f, -2.0f, 3.0f, -4.5f};
        auto is_negative = [](float x) { return x < 0.0f; };
        asc::std::replace_if(arr, arr + 4, is_negative, 0.0f);
        expect_eq("float arr[0] (was 1.5)", arr[0], 1.5f);
        expect_eq("float arr[1] (was -2.0)", arr[1], 0.0f);
        expect_eq("float arr[2] (was 3.0)", arr[2], 3.0f);
        expect_eq("float arr[3] (was -4.5)", arr[3], 0.0f);
    }

    // With vector iterators
    {
        std::vector<int> v = {10, 20, 30, 40, 50};
        auto greater_than_25 = [](int x) { return x > 25; };
        asc::std::replace_if(v.begin(), v.end(), greater_than_25, 0);
        expect_eq("vector v[0]", v[0], 10);
        expect_eq("vector v[1]", v[1], 20);
        expect_eq("vector v[2]", v[2], 0);
        expect_eq("vector v[3]", v[3], 0);
        expect_eq("vector v[4]", v[4], 0);
    }

    // Replace odd values with const ref new_value
    {
        int arr[] = {1, 2, 3, 4, 5};
        const int new_val = 99;
        auto is_odd = [](int x) { return x % 2 != 0; };
        asc::std::replace_if(arr, arr + 5, is_odd, new_val);
        expect_eq("odd-replaced arr[0]", arr[0], 99);
        expect_eq("odd-replaced arr[1]", arr[1], 2);
        expect_eq("odd-replaced arr[2]", arr[2], 99);
        expect_eq("odd-replaced arr[3]", arr[3], 4);
        expect_eq("odd-replaced arr[4]", arr[4], 99);
    }

    return g_failures == 0 ? 0 : 1;
}
