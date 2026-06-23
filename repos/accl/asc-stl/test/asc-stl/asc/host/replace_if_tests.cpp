#include "asc/std/__algorithm/replace_if.h"
#include <iostream>

static int g_failures = 0;

template <typename T>
static void expect_eq(const char* expr, T got, T expected) {
    bool ok = (got == expected);
    std::cout << "[host][replace_if] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

int main() {
    // Basic test: replace elements equal to 2 with 5 (mirrors CCCL test)
    {
        int ia[] = {0, 1, 2, 3, 4};
        int expected[] = {0, 1, 5, 3, 4};
        asc::std::replace_if(ia, ia + 5, [](int v) { return v == 2; }, 5);
        for (int i = 0; i < 5; ++i)
            expect_eq("ia[i] after replace_if (eq 2->5)", ia[i], expected[i]);
    }

    // No elements match predicate
    {
        int ia[] = {1, 3, 5, 7};
        int expected[] = {1, 3, 5, 7};
        asc::std::replace_if(ia, ia + 4, [](int v) { return v == 2; }, 99);
        for (int i = 0; i < 4; ++i)
            expect_eq("ia[i] after replace_if (no match)", ia[i], expected[i]);
    }

    // All elements match predicate
    {
        int ia[] = {2, 2, 2};
        int expected[] = {5, 5, 5};
        asc::std::replace_if(ia, ia + 3, [](int v) { return v == 2; }, 5);
        for (int i = 0; i < 3; ++i)
            expect_eq("ia[i] after replace_if (all match)", ia[i], expected[i]);
    }

    // Replace negative values with 0
    {
        int ia[] = {-3, 0, 5, -1, 7};
        int expected[] = {0, 0, 5, 0, 7};
        asc::std::replace_if(ia, ia + 5, [](int v) { return v < 0; }, 0);
        for (int i = 0; i < 5; ++i)
            expect_eq("ia[i] after replace_if (neg->0)", ia[i], expected[i]);
    }

    // Empty range: no elements should be modified
    {
        int ia[] = {1, 2, 3};
        asc::std::replace_if(ia, ia, [](int v) { return v == 2; }, 99);
        expect_eq("ia[0] after empty range replace_if", ia[0], 1);
        expect_eq("ia[1] after empty range replace_if", ia[1], 2);
        expect_eq("ia[2] after empty range replace_if", ia[2], 3);
    }

    // Single element matching
    {
        int ia[] = {5};
        asc::std::replace_if(ia, ia + 1, [](int v) { return v == 5; }, 0);
        expect_eq("ia[0] after replace_if (single match)", ia[0], 0);
    }

    // Single element not matching
    {
        int ia[] = {5};
        asc::std::replace_if(ia, ia + 1, [](int v) { return v == 3; }, 0);
        expect_eq("ia[0] after replace_if (single no match)", ia[0], 5);
    }

    // Replace even numbers with -1
    {
        int ia[] = {2, 3, 4, 5, 6};
        int expected[] = {-1, 3, -1, 5, -1};
        asc::std::replace_if(ia, ia + 5, [](int v) { return v % 2 == 0; }, -1);
        for (int i = 0; i < 5; ++i)
            expect_eq("ia[i] after replace_if (even->-1)", ia[i], expected[i]);
    }

    return g_failures == 0 ? 0 : 1;
}
