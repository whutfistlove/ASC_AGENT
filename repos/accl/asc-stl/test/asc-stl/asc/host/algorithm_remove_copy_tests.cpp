#include "asc/std/algorithm.remove_copy.h"
#include <iostream>

static int g_failures = 0;

template <typename T>
static void expect_eq(const char* expr, T got, T expected)
{
    bool ok = (got == expected);
    std::cout << "[host][remove_copy] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

static void expect_true(const char* expr, bool cond)
{
    std::cout << "[host][remove_copy] " << expr << " = " << (cond ? "true" : "false")
              << " (expected true) " << (cond ? "OK" : "FAIL") << std::endl;
    if (!cond) ++g_failures;
}

int main()
{
    // Basic test: remove 2 from {0,1,2,3,4,2,3,4,2}
    {
        int ia[] = {0, 1, 2, 3, 4, 2, 3, 4, 2};
        int ib[9] = {0};
        int expected[] = {0, 1, 3, 4, 3, 4};
        int* r = asc::std::remove_copy(ia, ia + 9, ib, 2);

        expect_true("basic: return == ib+6", r == ib + 6);
        for (int i = 0; i < 6; ++i) {
            expect_eq("basic: ib[i]", ib[i], expected[i]);
        }
        for (int i = 6; i < 9; ++i) {
            expect_eq("basic: ib[i] untouched", ib[i], 0);
        }
    }

    // Edge case: empty range
    {
        int ia[] = {1, 2, 3};
        int ib[3] = {0};
        int* r = asc::std::remove_copy(ia, ia, ib, 2);
        expect_true("empty range: return == ib", r == ib);
        expect_eq("empty range: ib[0] untouched", ib[0], 0);
    }

    // Edge case: no elements match
    {
        int ia[] = {1, 3, 5, 7};
        int ib[4] = {0};
        int* r = asc::std::remove_copy(ia, ia + 4, ib, 2);
        expect_true("no match: return == ib+4", r == ib + 4);
        int expected[] = {1, 3, 5, 7};
        for (int i = 0; i < 4; ++i) {
            expect_eq("no match: ib[i]", ib[i], expected[i]);
        }
    }

    // Edge case: all elements match
    {
        int ia[] = {2, 2, 2, 2};
        int ib[4] = {0};
        int* r = asc::std::remove_copy(ia, ia + 4, ib, 2);
        expect_true("all match: return == ib", r == ib);
        for (int i = 0; i < 4; ++i) {
            expect_eq("all match: ib[i] untouched", ib[i], 0);
        }
    }

    // Edge case: single element, matches
    {
        int ia[] = {5};
        int ib[1] = {0};
        int* r = asc::std::remove_copy(ia, ia + 1, ib, 5);
        expect_true("single match: return == ib", r == ib);
        expect_eq("single match: ib[0] untouched", ib[0], 0);
    }

    // Edge case: single element, does not match
    {
        int ia[] = {5};
        int ib[1] = {0};
        int* r = asc::std::remove_copy(ia, ia + 1, ib, 3);
        expect_true("single no match: return == ib+1", r == ib + 1);
        expect_eq("single no match: ib[0]", ib[0], 5);
    }

    // Float test
    {
        float ia[] = {1.0f, 2.0f, 3.0f, 2.0f, 4.0f};
        float ib[5] = {0.0f};
        float* r = asc::std::remove_copy(ia, ia + 5, ib, 2.0f);
        expect_true("float: return == ib+3", r == ib + 3);
        float expected[] = {1.0f, 3.0f, 4.0f};
        for (int i = 0; i < 3; ++i) {
            expect_eq("float: ib[i]", ib[i], expected[i]);
        }
    }

    // Negative values
    {
        int ia[] = {-3, -1, 0, -3, 2, -3};
        int ib[6] = {0};
        int expected[] = {-1, 0, 2};
        int* r = asc::std::remove_copy(ia, ia + 6, ib, -3);
        expect_true("negative: return == ib+3", r == ib + 3);
        for (int i = 0; i < 3; ++i) {
            expect_eq("negative: ib[i]", ib[i], expected[i]);
        }
    }

    return g_failures == 0 ? 0 : 1;
}
