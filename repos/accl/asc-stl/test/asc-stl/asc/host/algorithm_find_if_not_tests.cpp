#include "asc/std/algorithm.find_if_not.h"
#include <iostream>
#include <vector>

static int g_failures = 0;

static void expect_eq_int(const char* expr, int got, int expected)
{
    bool ok = (got == expected);
    std::cout << "[host][find_if_not] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

static void expect_true(const char* expr, bool cond)
{
    std::cout << "[host][find_if_not] " << expr << " = " << (cond ? "true" : "false")
              << " (expected true) " << (cond ? "OK" : "FAIL") << std::endl;
    if (!cond) ++g_failures;
}

int main()
{
    // Basic: find first odd in even-first array
    {
        int arr[] = {2, 4, 6, 7, 8, 10};
        auto it = asc::std::find_if_not(arr, arr + 6, [](int x) { return x % 2 == 0; });
        expect_true("first not-even points to 7", it == arr + 3);
        expect_eq_int("*it", *it, 7);
    }

    // All satisfy predicate → returns last
    {
        int arr[] = {2, 4, 6, 8};
        auto it = asc::std::find_if_not(arr, arr + 4, [](int x) { return x % 2 == 0; });
        expect_true("all even → returns last", it == arr + 4);
    }

    // First element does not satisfy → returns first
    {
        int arr[] = {1, 3, 5, 7};
        auto it = asc::std::find_if_not(arr, arr + 4, [](int x) { return x % 2 == 0; });
        expect_true("first not-even at begin", it == arr);
        expect_eq_int("*it", *it, 1);
    }

    // Empty range → returns first
    {
        int arr[] = {1, 2, 3};
        auto it = asc::std::find_if_not(arr, arr, [](int x) { return x > 0; });
        expect_true("empty range → returns first", it == arr);
    }

    // With vector iterators
    {
        std::vector<int> v = {10, 20, 25, 30, 40};
        auto it = asc::std::find_if_not(v.begin(), v.end(), [](int x) { return x < 25; });
        expect_true("first not < 25 is at index 2", it == v.begin() + 2);
        expect_eq_int("*it", *it, 25);
    }

    // Predicate: always true → returns last
    {
        int arr[] = {1, 2, 3};
        auto it = asc::std::find_if_not(arr, arr + 3, [](int) { return true; });
        expect_true("always-true pred → returns last", it == arr + 3);
    }

    // Predicate: always false → returns first
    {
        int arr[] = {1, 2, 3};
        auto it = asc::std::find_if_not(arr, arr + 3, [](int) { return false; });
        expect_true("always-false pred → returns first", it == arr);
        expect_eq_int("*it", *it, 1);
    }

    // Negative values
    {
        int arr[] = {-5, -3, 0, 1, 2};
        auto it = asc::std::find_if_not(arr, arr + 5, [](int x) { return x < 0; });
        expect_true("first not-negative at index 2", it == arr + 2);
        expect_eq_int("*it", *it, 0);
    }

    return g_failures == 0 ? 0 : 1;
}
