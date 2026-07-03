#include "asc/std/algorithm.replace.h"
#include <iostream>
#include <vector>

static int g_failures = 0;

template <typename T>
static void expect_eq(const char* expr, T got, T expected)
{
    bool ok = (got == expected);
    std::cout << "[host][replace] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

static void expect_true(const char* expr, bool cond)
{
    std::cout << "[host][replace] " << expr << " = " << (cond ? "true" : "false")
              << " (expected true) " << (cond ? "OK" : "FAIL") << std::endl;
    if (!cond) ++g_failures;
}

int main()
{
    // Basic test: replace some elements in an int array
    {
        int arr[] = {1, 2, 3, 2, 5};
        asc::std::replace(arr, arr + 5, 2, 99);
        expect_eq("arr[0] after replace(2->99)", arr[0], 1);
        expect_eq("arr[1] after replace(2->99)", arr[1], 99);
        expect_eq("arr[2] after replace(2->99)", arr[2], 3);
        expect_eq("arr[3] after replace(2->99)", arr[3], 99);
        expect_eq("arr[4] after replace(2->99)", arr[4], 5);
    }

    // No elements match old_value
    {
        int arr[] = {10, 20, 30};
        asc::std::replace(arr, arr + 3, 999, 0);
        expect_eq("arr[0] no match", arr[0], 10);
        expect_eq("arr[1] no match", arr[1], 20);
        expect_eq("arr[2] no match", arr[2], 30);
    }

    // All elements match old_value
    {
        int arr[] = {7, 7, 7, 7};
        asc::std::replace(arr, arr + 4, 7, 42);
        expect_eq("arr[0] all match", arr[0], 42);
        expect_eq("arr[1] all match", arr[1], 42);
        expect_eq("arr[2] all match", arr[2], 42);
        expect_eq("arr[3] all match", arr[3], 42);
    }

    // Empty range (first == last)
    {
        int arr[] = {1, 2, 3};
        asc::std::replace(arr, arr, 1, 99);
        expect_eq("arr[0] empty range", arr[0], 1);
        expect_eq("arr[1] empty range", arr[1], 2);
        expect_eq("arr[2] empty range", arr[2], 3);
    }

    // Float type
    {
        float arr[] = {1.5f, 2.0f, 3.5f, 2.0f};
        asc::std::replace(arr, arr + 4, 2.0f, 9.9f);
        expect_eq("arr[0] float replace", arr[0], 1.5f);
        expect_eq("arr[1] float replace", arr[1], 9.9f);
        expect_eq("arr[2] float replace", arr[2], 3.5f);
        expect_eq("arr[3] float replace", arr[3], 9.9f);
    }

    // Using std::vector iterators
    {
        std::vector<int> v = {5, 10, 5, 20, 5};
        asc::std::replace(v.begin(), v.end(), 5, 0);
        expect_true("v == {0,10,0,20,0}",
            v[0] == 0 && v[1] == 10 && v[2] == 0 && v[3] == 20 && v[4] == 0);
    }

    // Single element range, matches
    {
        int arr[] = {42};
        asc::std::replace(arr, arr + 1, 42, 100);
        expect_eq("arr[0] single match", arr[0], 100);
    }

    // Single element range, no match
    {
        int arr[] = {42};
        asc::std::replace(arr, arr + 1, 99, 100);
        expect_eq("arr[0] single no match", arr[0], 42);
    }

    // old_value == new_value (no-op effectively)
    {
        int arr[] = {1, 2, 3};
        asc::std::replace(arr, arr + 3, 2, 2);
        expect_eq("arr[0] old==new", arr[0], 1);
        expect_eq("arr[1] old==new", arr[1], 2);
        expect_eq("arr[2] old==new", arr[2], 3);
    }

    return g_failures == 0 ? 0 : 1;
}
