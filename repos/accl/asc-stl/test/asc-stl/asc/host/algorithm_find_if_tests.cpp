#include "asc/std/algorithm.find_if.h"
#include <iostream>
#include <vector>

static int g_failures = 0;

template <typename T>
static void expect_eq(const char* expr, T got, T expected)
{
    bool ok = (got == expected);
    std::cout << "[host][find_if] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

static void expect_true(const char* expr, bool cond)
{
    std::cout << "[host][find_if] " << expr << " = " << (cond ? "true" : "false")
              << " (expected true) " << (cond ? "OK" : "FAIL") << std::endl;
    if (!cond) ++g_failures;
}

int main()
{
    // Basic: find_if finds first element > 3
    {
        int arr[] = {1, 2, 3, 4, 5};
        auto it = asc::std::find_if(arr, arr + 5, [](int x) { return x > 3; });
        expect_true("find_if finds 4", it == arr + 3);
        expect_eq("value at found position", *it, 4);
    }

    // No element matches: returns last
    {
        int arr[] = {1, 2, 3};
        auto it = asc::std::find_if(arr, arr + 3, [](int x) { return x > 10; });
        expect_true("find_if returns last when no match", it == arr + 3);
    }

    // First element matches
    {
        int arr[] = {10, 2, 3};
        auto it = asc::std::find_if(arr, arr + 3, [](int x) { return x > 5; });
        expect_true("find_if finds first element", it == arr);
        expect_eq("value at first position", *it, 10);
    }

    // Last element matches
    {
        int arr[] = {1, 2, 30};
        auto it = asc::std::find_if(arr, arr + 3, [](int x) { return x > 20; });
        expect_true("find_if finds last element", it == arr + 2);
        expect_eq("value at last position", *it, 30);
    }

    // Empty range: returns last
    {
        int arr[] = {1, 2, 3};
        auto it = asc::std::find_if(arr, arr, [](int x) { return x > 0; });
        expect_true("find_if on empty range returns last", it == arr);
    }

    // With vector iterators
    {
        std::vector<int> v = {5, 10, 15, 20};
        auto it = asc::std::find_if(v.begin(), v.end(), [](int x) { return x >= 15; });
        expect_true("find_if with vector finds 15", it == v.begin() + 2);
        expect_eq("vector value at found", *it, 15);
    }

    // Negative values
    {
        int arr[] = {-5, -3, 0, 2, 7};
        auto it = asc::std::find_if(arr, arr + 5, [](int x) { return x < 0; });
        expect_true("find_if finds first negative", it == arr);
        expect_eq("first negative value", *it, -5);
    }

    // Predicate checks for even numbers
    {
        int arr[] = {1, 3, 5, 4, 7};
        auto it = asc::std::find_if(arr, arr + 5, [](int x) { return x % 2 == 0; });
        expect_true("find_if finds first even", it == arr + 3);
        expect_eq("first even value", *it, 4);
    }

    // All elements match: returns first
    {
        int arr[] = {2, 4, 6, 8};
        auto it = asc::std::find_if(arr, arr + 4, [](int x) { return x % 2 == 0; });
        expect_true("find_if all match returns first", it == arr);
        expect_eq("all-match first value", *it, 2);
    }

    // Single element that matches
    {
        int arr[] = {42};
        auto it = asc::std::find_if(arr, arr + 1, [](int x) { return x == 42; });
        expect_true("find_if single match", it == arr);
        expect_eq("single match value", *it, 42);
    }

    // Single element that does not match
    {
        int arr[] = {7};
        auto it = asc::std::find_if(arr, arr + 1, [](int x) { return x > 100; });
        expect_true("find_if single no match returns last", it == arr + 1);
    }

    return g_failures == 0 ? 0 : 1;
}
