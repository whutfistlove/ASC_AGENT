// ACCL-side host test for replace_copy, migrated from the CCCL replace_copy.pass.cpp test.
//
// replace_copy is a range-based algorithm: copies [first,last) to result,
// replacing elements equal to old_value with new_value. Returns output iterator
// past the last written element.
// The test compares results to INDEPENDENT expected values.
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
    // Basic test from CCCL: replace 2 with 5 in {0,1,2,3,4}
    {
        const int N = 5;
        int ia[N] = {0, 1, 2, 3, 4};
        int ib[N] = {0, 0, 0, 0, 0};
        const int expected[N] = {0, 1, 5, 3, 4};

        int* r = asc::std::replace_copy(ia, ia + N, ib, 2, 5);

        expect_true("basic: return iter == ib + N", r == ib + N);
        for (int i = 0; i < N; ++i)
        {
            expect_eq("basic: ib[i]", ib[i], expected[i]);
        }
    }

    // No elements match old_value
    {
        const int N = 4;
        int ia[N] = {0, 1, 3, 4};
        int ib[N] = {-1, -1, -1, -1};
        const int expected[N] = {0, 1, 3, 4};

        int* r = asc::std::replace_copy(ia, ia + N, ib, 2, 5);

        expect_true("no-match: return iter == ib + N", r == ib + N);
        for (int i = 0; i < N; ++i)
        {
            expect_eq("no-match: ib[i]", ib[i], expected[i]);
        }
    }

    // All elements match old_value
    {
        const int N = 3;
        int ia[N] = {2, 2, 2};
        int ib[N] = {0, 0, 0};
        const int expected[N] = {5, 5, 5};

        int* r = asc::std::replace_copy(ia, ia + N, ib, 2, 5);

        expect_true("all-match: return iter == ib + N", r == ib + N);
        for (int i = 0; i < N; ++i)
        {
            expect_eq("all-match: ib[i]", ib[i], expected[i]);
        }
    }

    // Empty range
    {
        int ia[1] = {42};
        int ib[1] = {-1};

        int* r = asc::std::replace_copy(ia, ia, ib, 42, 99);

        expect_true("empty: return iter == ib", r == ib);
        expect_eq("empty: ib[0] untouched", ib[0], -1);
    }

    // Float test
    {
        const int N = 4;
        float ia[N] = {1.0f, 2.0f, 3.0f, 2.0f};
        float ib[N] = {0.0f, 0.0f, 0.0f, 0.0f};
        const float expected[N] = {1.0f, 99.0f, 3.0f, 99.0f};

        float* r = asc::std::replace_copy(ia, ia + N, ib, 2.0f, 99.0f);

        expect_true("float: return iter == ib + N", r == ib + N);
        for (int i = 0; i < N; ++i)
        {
            expect_eq("float: ib[i]", ib[i], expected[i]);
        }
    }

    // old_value == new_value (replace with itself)
    {
        const int N = 3;
        int ia[N] = {1, 2, 3};
        int ib[N] = {0, 0, 0};
        const int expected[N] = {1, 2, 3};

        int* r = asc::std::replace_copy(ia, ia + N, ib, 2, 2);

        expect_true("same-old-new: return iter == ib + N", r == ib + N);
        for (int i = 0; i < N; ++i)
        {
            expect_eq("same-old-new: ib[i]", ib[i], expected[i]);
        }
    }

    // Negative values
    {
        const int N = 4;
        int ia[N] = {-1, -2, -3, -2};
        int ib[N] = {0, 0, 0, 0};
        const int expected[N] = {-1, 0, -3, 0};

        int* r = asc::std::replace_copy(ia, ia + N, ib, -2, 0);

        expect_true("negative: return iter == ib + N", r == ib + N);
        for (int i = 0; i < N; ++i)
        {
            expect_eq("negative: ib[i]", ib[i], expected[i]);
        }
    }

    return g_failures == 0 ? 0 : 1;
}
