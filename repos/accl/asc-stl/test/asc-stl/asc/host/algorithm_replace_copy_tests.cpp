#include "asc/std/__algorithm/replace_copy.h"
#include <iostream>

static int g_failures = 0;

template <typename T>
static void expect_eq(const char* expr, T got, T expected)
{
    bool ok = (got == expected);
    std::cout << "[host][replace_copy] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

static void expect_true(const char* expr, bool cond)
{
    std::cout << "[host][replace_copy] " << expr << " = " << (cond ? "true" : "false")
              << " (expected true) " << (cond ? "OK" : "FAIL") << std::endl;
    if (!cond) ++g_failures;
}

int main()
{
    // Test 1: Basic replace_copy with int array
    {
        int src[] = {1, 2, 3, 2, 5};
        int dst[5] = {};
        int* result = asc::std::replace_copy(src, src + 5, dst, 2, 99);
        expect_eq("basic dst[0]", dst[0], 1);
        expect_eq("basic dst[1]", dst[1], 99);
        expect_eq("basic dst[2]", dst[2], 3);
        expect_eq("basic dst[3]", dst[3], 99);
        expect_eq("basic dst[4]", dst[4], 5);
        expect_true("basic result == dst + 5", result == dst + 5);
    }

    // Test 2: No elements match old_value
    {
        int src[] = {1, 3, 5, 7};
        int dst[4] = {};
        int* result = asc::std::replace_copy(src, src + 4, dst, 2, 99);
        expect_eq("no-match dst[0]", dst[0], 1);
        expect_eq("no-match dst[1]", dst[1], 3);
        expect_eq("no-match dst[2]", dst[2], 5);
        expect_eq("no-match dst[3]", dst[3], 7);
        expect_true("no-match result == dst + 4", result == dst + 4);
    }

    // Test 3: All elements match old_value
    {
        int src[] = {5, 5, 5};
        int dst[3] = {};
        int* result = asc::std::replace_copy(src, src + 3, dst, 5, 0);
        expect_eq("all-match dst[0]", dst[0], 0);
        expect_eq("all-match dst[1]", dst[1], 0);
        expect_eq("all-match dst[2]", dst[2], 0);
        expect_true("all-match result == dst + 3", result == dst + 3);
    }

    // Test 4: Single element - matches
    {
        int src[] = {42};
        int dst[1] = {};
        int* result = asc::std::replace_copy(src, src + 1, dst, 42, 7);
        expect_eq("single-match dst[0]", dst[0], 7);
        expect_true("single-match result == dst + 1", result == dst + 1);
    }

    // Test 5: Single element - no match
    {
        int src[] = {42};
        int dst[1] = {};
        int* result = asc::std::replace_copy(src, src + 1, dst, 99, 7);
        expect_eq("single-nomatch dst[0]", dst[0], 42);
        expect_true("single-nomatch result == dst + 1", result == dst + 1);
    }

    // Test 6: Empty range
    {
        int src[] = {1, 2, 3};
        int dst[3] = {-1, -1, -1};
        int* result = asc::std::replace_copy(src, src, dst, 2, 99);
        expect_eq("empty dst[0]", dst[0], -1);
        expect_true("empty result == dst", result == dst);
    }

    // Test 7: With float type
    {
        float src[] = {1.0f, 2.5f, 3.0f, 2.5f};
        float dst[4] = {};
        float* result = asc::std::replace_copy(src, src + 4, dst, 2.5f, -1.0f);
        expect_eq("float dst[0]", dst[0], 1.0f);
        expect_eq("float dst[1]", dst[1], -1.0f);
        expect_eq("float dst[2]", dst[2], 3.0f);
        expect_eq("float dst[3]", dst[3], -1.0f);
        expect_true("float result == dst + 4", result == dst + 4);
    }

    // Test 8: old_value equals new_value (identity replacement)
    {
        int src[] = {1, 2, 2, 3};
        int dst[4] = {};
        int* result = asc::std::replace_copy(src, src + 4, dst, 2, 2);
        expect_eq("identity dst[0]", dst[0], 1);
        expect_eq("identity dst[1]", dst[1], 2);
        expect_eq("identity dst[2]", dst[2], 2);
        expect_eq("identity dst[3]", dst[3], 3);
        expect_true("identity result == dst + 4", result == dst + 4);
    }

    // Test 9: Negative values
    {
        int src[] = {-1, -2, -3, -2, 0};
        int dst[5] = {};
        int* result = asc::std::replace_copy(src, src + 5, dst, -2, 100);
        expect_eq("neg dst[0]", dst[0], -1);
        expect_eq("neg dst[1]", dst[1], 100);
        expect_eq("neg dst[2]", dst[2], -3);
        expect_eq("neg dst[3]", dst[3], 100);
        expect_eq("neg dst[4]", dst[4], 0);
        expect_true("neg result == dst + 5", result == dst + 5);
    }

    return g_failures == 0 ? 0 : 1;
}
