#include "asc/std/algorithm.replace_copy_if.h"
#include <iostream>
#include <vector>

static int g_failures = 0;

template <typename T>
static void expect_eq(const char* expr, T got, T expected)
{
    bool ok = (got == expected);
    std::cout << "[host][replace_copy_if] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

static void expect_true(const char* expr, bool cond)
{
    std::cout << "[host][replace_copy_if] " << expr << " = " << (cond ? "true" : "false")
              << " (expected true) " << (cond ? "OK" : "FAIL") << std::endl;
    if (!cond) ++g_failures;
}

int main()
{
    // Test 1: Basic - replace negative values with 0
    {
        int src[] = {1, -2, 3, -4, 5};
        int dst[5] = {};
        auto pred = [](int x) { return x < 0; };
        auto result = asc::std::replace_copy_if(src, src + 5, dst, pred, 0);
        expect_eq("dst[0]", dst[0], 1);
        expect_eq("dst[1]", dst[1], 0);
        expect_eq("dst[2]", dst[2], 3);
        expect_eq("dst[3]", dst[3], 0);
        expect_eq("dst[4]", dst[4], 5);
        expect_true("result == dst + 5", result == dst + 5);
    }

    // Test 2: Predicate always true - all replaced
    {
        int src[] = {1, 2, 3};
        int dst[3] = {};
        auto pred = [](int) { return true; };
        auto result = asc::std::replace_copy_if(src, src + 3, dst, pred, 99);
        expect_eq("all-replaced dst[0]", dst[0], 99);
        expect_eq("all-replaced dst[1]", dst[1], 99);
        expect_eq("all-replaced dst[2]", dst[2], 99);
        expect_true("all-replaced result == dst + 3", result == dst + 3);
    }

    // Test 3: Predicate always false - none replaced (plain copy)
    {
        int src[] = {10, 20, 30};
        int dst[3] = {};
        auto pred = [](int) { return false; };
        auto result = asc::std::replace_copy_if(src, src + 3, dst, pred, 99);
        expect_eq("none-replaced dst[0]", dst[0], 10);
        expect_eq("none-replaced dst[1]", dst[1], 20);
        expect_eq("none-replaced dst[2]", dst[2], 30);
        expect_true("none-replaced result == dst + 3", result == dst + 3);
    }

    // Test 4: Empty range
    {
        int src[] = {1, 2, 3};
        int dst[3] = {0, 0, 0};
        auto pred = [](int) { return true; };
        auto result = asc::std::replace_copy_if(src, src, dst, pred, 99);
        expect_true("empty-range result == dst", result == dst);
        expect_eq("empty-range dst[0] unchanged", dst[0], 0);
    }

    // Test 5: With std::vector iterators
    {
        std::vector<float> src = {1.5f, -2.5f, 3.5f, -4.5f};
        std::vector<float> dst(4, 0.0f);
        auto pred = [](float x) { return x < 0.0f; };
        auto result = asc::std::replace_copy_if(src.begin(), src.end(), dst.begin(), pred, 0.0f);
        expect_eq("vector dst[0]", dst[0], 1.5f);
        expect_eq("vector dst[1]", dst[1], 0.0f);
        expect_eq("vector dst[2]", dst[2], 3.5f);
        expect_eq("vector dst[3]", dst[3], 0.0f);
        expect_true("vector result == dst.end()", result == dst.end());
    }

    // Test 6: Replace even numbers with -1
    {
        int src[] = {1, 2, 3, 4, 5, 6};
        int dst[6] = {};
        auto pred = [](int x) { return x % 2 == 0; };
        auto result = asc::std::replace_copy_if(src, src + 6, dst, pred, -1);
        expect_eq("even-replaced dst[0]", dst[0], 1);
        expect_eq("even-replaced dst[1]", dst[1], -1);
        expect_eq("even-replaced dst[2]", dst[2], 3);
        expect_eq("even-replaced dst[3]", dst[3], -1);
        expect_eq("even-replaced dst[4]", dst[4], 5);
        expect_eq("even-replaced dst[5]", dst[5], -1);
    }

    return g_failures == 0 ? 0 : 1;
}
