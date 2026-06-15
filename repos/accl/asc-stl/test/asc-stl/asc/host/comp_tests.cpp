#include "asc/std/__algorithm/comp.h"
#include <iostream>

static int g_failures = 0;

static void expect_eq(const char* expr, bool got, bool expected)
{
    bool ok = (got == expected);
    std::cout << "[host][comp] " << expr << " = " << (got ? "true" : "false")
              << " (expected " << (expected ? "true" : "false") << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

int main()
{
    asc::std::__equal_to eq;
    asc::std::__less ls;

    // __equal_to tests
    {
        expect_eq("__equal_to()(3, 3)", eq(3, 3), true);
        expect_eq("__equal_to()(3, 4)", eq(3, 4), false);
        expect_eq("__equal_to()(-1, -1)", eq(-1, -1), true);
        expect_eq("__equal_to()(0, 0)", eq(0, 0), true);
        expect_eq("__equal_to()(0, 1)", eq(0, 1), false);
    }

    // __equal_to with mixed types
    {
        expect_eq("__equal_to()(1, 1.0)", eq(1, 1.0), true);
        expect_eq("__equal_to()(1, 1.5)", eq(1, 1.5), false);
    }

    // __less tests
    {
        expect_eq("__less()(1, 2)", ls(1, 2), true);
        expect_eq("__less()(2, 1)", ls(2, 1), false);
        expect_eq("__less()(1, 1)", ls(1, 1), false);
        expect_eq("__less()(-5, -3)", ls(-5, -3), true);
        expect_eq("__less()(-3, -5)", ls(-3, -5), false);
        expect_eq("__less()(0, 1)", ls(0, 1), true);
    }

    // __less with mixed types
    {
        expect_eq("__less()(1, 2.0)", ls(1, 2.0), true);
        expect_eq("__less()(2.0, 1)", ls(2.0, 1), false);
    }

    // floating point
    {
        expect_eq("__equal_to()(1.5f, 1.5f)", eq(1.5f, 1.5f), true);
        expect_eq("__equal_to()(1.5f, 2.5f)", eq(1.5f, 2.5f), false);
        expect_eq("__less()(1.5f, 2.5f)", ls(1.5f, 2.5f), true);
        expect_eq("__less()(2.5f, 1.5f)", ls(2.5f, 1.5f), false);
    }

    return g_failures == 0 ? 0 : 1;
}
