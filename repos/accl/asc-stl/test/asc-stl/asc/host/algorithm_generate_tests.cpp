#include "asc/std/algorithm.generate.h"
#include <iostream>

static int g_failures = 0;

template <typename T>
static void expect_eq(const char* expr, T got, T expected)
{
    bool ok = (got == expected);
    std::cout << "[host][generate] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

int main()
{
    // Test 1: constant generator
    {
        int arr[5] = {0, 0, 0, 0, 0};
        asc::std::generate(arr, arr + 5, []() { return 42; });
        for (int i = 0; i < 5; ++i)
            expect_eq("arr[i] after constant gen", arr[i], 42);
    }

    // Test 2: incrementing counter generator
    {
        int arr[5] = {0, 0, 0, 0, 0};
        int counter = 0;
        asc::std::generate(arr, arr + 5, [&counter]() { return counter++; });
        for (int i = 0; i < 5; ++i)
            expect_eq("arr[i] after counter gen", arr[i], i);
    }

    // Test 3: empty range (first == last), should be no-op
    {
        int arr[3] = {1, 2, 3};
        asc::std::generate(arr, arr, []() { return 99; });
        expect_eq("arr[0] after empty range gen", arr[0], 1);
        expect_eq("arr[1] after empty range gen", arr[1], 2);
        expect_eq("arr[2] after empty range gen", arr[2], 3);
    }

    // Test 4: single element range
    {
        int arr[1] = {0};
        asc::std::generate(arr, arr + 1, []() { return 7; });
        expect_eq("arr[0] after single-element gen", arr[0], 7);
    }

    // Test 5: floating point generator
    {
        float arr[4] = {0.0f, 0.0f, 0.0f, 0.0f};
        float val = 1.5f;
        asc::std::generate(arr, arr + 4, [&val]() { float r = val; val += 1.0f; return r; });
        expect_eq("arr[0] after float gen", arr[0], 1.5f);
        expect_eq("arr[1] after float gen", arr[1], 2.5f);
        expect_eq("arr[2] after float gen", arr[2], 3.5f);
        expect_eq("arr[3] after float gen", arr[3], 4.5f);
    }

    return g_failures == 0 ? 0 : 1;
}
