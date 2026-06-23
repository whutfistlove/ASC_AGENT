#include "asc/std/__algorithm/replace.h"
#include <iostream>

static int g_failures = 0;

static void expect_arr_eq(const char* label, const int* got, const int* expected, int n)
{
    bool all_ok = true;
    for (int i = 0; i < n; ++i)
    {
        if (got[i] != expected[i])
        {
            all_ok = false;
            break;
        }
    }
    std::cout << "[host][replace] " << label << " = {";
    for (int i = 0; i < n; ++i)
    {
        std::cout << got[i];
        if (i < n - 1) std::cout << ", ";
    }
    std::cout << "} (expected {";
    for (int i = 0; i < n; ++i)
    {
        std::cout << expected[i];
        if (i < n - 1) std::cout << ", ";
    }
    std::cout << "}) " << (all_ok ? "OK" : "FAIL") << std::endl;
    if (!all_ok) ++g_failures;
}

int main()
{
    // Basic test from CCCL: replace 2 with 5 in {0,1,2,3,4}
    {
        int ia[] = {0, 1, 2, 3, 4};
        int expected[] = {0, 1, 5, 3, 4};
        asc::std::replace(ia, ia + 5, 2, 5);
        expect_arr_eq("replace({0,1,2,3,4}, 2, 5)", ia, expected, 5);
    }

    // No matches
    {
        int ia[] = {0, 1, 3, 4};
        int expected[] = {0, 1, 3, 4};
        asc::std::replace(ia, ia + 4, 2, 5);
        expect_arr_eq("replace({0,1,3,4}, 2, 5) no match", ia, expected, 4);
    }

    // All match
    {
        int ia[] = {2, 2, 2};
        int expected[] = {5, 5, 5};
        asc::std::replace(ia, ia + 3, 2, 5);
        expect_arr_eq("replace({2,2,2}, 2, 5) all match", ia, expected, 3);
    }

    // Single element - match
    {
        int ia[] = {7};
        int expected[] = {99};
        asc::std::replace(ia, ia + 1, 7, 99);
        expect_arr_eq("replace({7}, 7, 99) single match", ia, expected, 1);
    }

    // Single element - no match
    {
        int ia[] = {3};
        int expected[] = {3};
        asc::std::replace(ia, ia + 1, 7, 99);
        expect_arr_eq("replace({3}, 7, 99) single no match", ia, expected, 1);
    }

    // Empty range
    {
        int ia[] = {1, 2, 3};
        int expected[] = {1, 2, 3};
        asc::std::replace(ia, ia, 2, 5);
        expect_arr_eq("replace(empty range)", ia, expected, 3);
    }

    // Multiple occurrences
    {
        int ia[] = {1, 2, 3, 2, 4, 2};
        int expected[] = {1, 0, 3, 0, 4, 0};
        asc::std::replace(ia, ia + 6, 2, 0);
        expect_arr_eq("replace({1,2,3,2,4,2}, 2, 0) multiple", ia, expected, 6);
    }

    // Negative values
    {
        int ia[] = {-1, -3, -3, 0, 5};
        int expected[] = {-1, 0, 0, 0, 5};
        asc::std::replace(ia, ia + 5, -3, 0);
        expect_arr_eq("replace({-1,-3,-3,0,5}, -3, 0) negative", ia, expected, 5);
    }

    return g_failures == 0 ? 0 : 1;
}
