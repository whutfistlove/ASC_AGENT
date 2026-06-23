#include "asc/std/__algorithm/find_if.h"
#include <iostream>

static int g_failures = 0;

template <typename T>
static void expect_eq(const char* expr, T got, T expected)
{
    bool ok = (got == expected);
    std::cout << "[host][find_if] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

int main()
{
    // Test 1: first element matches
    {
        int arr[] = {2, 4, 6, 8};
        auto pred = [](int v) { return v == 2; };
        int* it = asc::std::find_if(arr, arr + 4, pred);
        expect_eq("find_if first match: *it", *it, 2);
        expect_eq("find_if first match: index", static_cast<int>(it - arr), 0);
    }

    // Test 2: empty range returns last
    {
        int arr[] = {2, 4, 6, 8};
        auto pred = [](int v) { return v == 2; };
        int* it = asc::std::find_if(arr, arr, pred);
        expect_eq("find_if empty range: index", static_cast<int>(it - arr), 0);
    }

    // Test 3: multiple matches returns first
    {
        int arr[] = {2, 4, 4, 8};
        auto pred = [](int v) { return v == 4; };
        int* it = asc::std::find_if(arr, arr + 4, pred);
        expect_eq("find_if multiple match: *it", *it, 4);
        expect_eq("find_if multiple match: index", static_cast<int>(it - arr), 1);
    }

    // Test 4: middle element matches
    {
        int arr[] = {2, 4, 6, 8};
        auto pred = [](int v) { return v == 6; };
        int* it = asc::std::find_if(arr, arr + 4, pred);
        expect_eq("find_if middle match: *it", *it, 6);
        expect_eq("find_if middle match: index", static_cast<int>(it - arr), 2);
    }

    // Test 5: last element matches
    {
        int arr[] = {2, 4, 6, 8};
        auto pred = [](int v) { return v == 8; };
        int* it = asc::std::find_if(arr, arr + 4, pred);
        expect_eq("find_if last match: *it", *it, 8);
        expect_eq("find_if last match: index", static_cast<int>(it - arr), 3);
    }

    // Test 6: no match returns last
    {
        int arr[] = {2, 4, 6, 8};
        auto pred = [](int v) { return v == 10; };
        int* it = asc::std::find_if(arr, arr + 4, pred);
        expect_eq("find_if no match: index", static_cast<int>(it - arr), 4);
    }

    return g_failures == 0 ? 0 : 1;
}
