#include "asc/std/algorithm.copy_if.h"
#include <iostream>
#include <vector>

static int g_failures = 0;

template <typename T>
static void expect_eq(const char* expr, T got, T expected)
{
    bool ok = (got == expected);
    std::cout << "[host][copy_if] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

int main()
{
    // Test 1: Copy even numbers
    {
        int src[] = {1, 2, 3, 4, 5, 6};
        int dst[6] = {};
        auto pred = [](int x) { return x % 2 == 0; };
        auto result = asc::std::copy_if(src, src + 6, dst, pred);
        int count = static_cast<int>(result - dst);
        expect_eq("copy_if even count", count, 3);
        expect_eq("dst[0]", dst[0], 2);
        expect_eq("dst[1]", dst[1], 4);
        expect_eq("dst[2]", dst[2], 6);
    }

    // Test 2: All elements match predicate
    {
        int src[] = {10, 20, 30};
        int dst[3] = {};
        auto pred = [](int) { return true; };
        auto result = asc::std::copy_if(src, src + 3, dst, pred);
        int count = static_cast<int>(result - dst);
        expect_eq("copy_if all match count", count, 3);
        expect_eq("dst[0]", dst[0], 10);
        expect_eq("dst[1]", dst[1], 20);
        expect_eq("dst[2]", dst[2], 30);
    }

    // Test 3: No elements match predicate
    {
        int src[] = {1, 3, 5};
        int dst[3] = {};
        auto pred = [](int x) { return x % 2 == 0; };
        auto result = asc::std::copy_if(src, src + 3, dst, pred);
        int count = static_cast<int>(result - dst);
        expect_eq("copy_if none match count", count, 0);
    }

    // Test 4: Empty range (first == last)
    {
        int src[] = {1, 2, 3};
        int dst[3] = {};
        auto pred = [](int) { return true; };
        auto result = asc::std::copy_if(src, src, dst, pred);
        int count = static_cast<int>(result - dst);
        expect_eq("copy_if empty range count", count, 0);
    }

    // Test 5: Copy positive numbers from mixed float array
    {
        float src[] = {-1.5f, 2.0f, -3.0f, 4.5f, 0.0f};
        float dst[5] = {};
        auto pred = [](float x) { return x > 0.0f; };
        auto result = asc::std::copy_if(src, src + 5, dst, pred);
        int count = static_cast<int>(result - dst);
        expect_eq("copy_if positive count", count, 2);
        expect_eq("dst[0]", dst[0], 2.0f);
        expect_eq("dst[1]", dst[1], 4.5f);
    }

    // Test 6: Using std::vector iterators
    {
        std::vector<int> src = {5, 10, 15, 20, 25};
        std::vector<int> dst(5, 0);
        auto pred = [](int x) { return x >= 15; };
        auto result = asc::std::copy_if(src.begin(), src.end(), dst.begin(), pred);
        int count = static_cast<int>(result - dst.begin());
        expect_eq("copy_if >=15 count", count, 3);
        expect_eq("dst[0]", dst[0], 15);
        expect_eq("dst[1]", dst[1], 20);
        expect_eq("dst[2]", dst[2], 25);
    }

    // Test 7: Single element matching
    {
        int src[] = {42};
        int dst[1] = {};
        auto pred = [](int x) { return x == 42; };
        auto result = asc::std::copy_if(src, src + 1, dst, pred);
        int count = static_cast<int>(result - dst);
        expect_eq("copy_if single match count", count, 1);
        expect_eq("dst[0]", dst[0], 42);
    }

    // Test 8: Single element not matching
    {
        int src[] = {7};
        int dst[1] = {};
        auto pred = [](int x) { return x == 42; };
        auto result = asc::std::copy_if(src, src + 1, dst, pred);
        int count = static_cast<int>(result - dst);
        expect_eq("copy_if single no match count", count, 0);
    }

    return g_failures == 0 ? 0 : 1;
}
