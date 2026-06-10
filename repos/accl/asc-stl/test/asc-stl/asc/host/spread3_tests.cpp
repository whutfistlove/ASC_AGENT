#include "asc/std/__numeric/spread3.h"
#include <iostream>

static int g_failures = 0;

template <typename T>
static void expect_eq(const char* expr, T got, T expected)
{
    bool ok = (got == expected);
    std::cout << "[host][spread3] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

int main()
{
    // Case 1: spread3(3, 1, 2) -> lo=1, width=2
    {
        int lo = 0, width = 0;
        asc::std::spread3(3, 1, 2, lo, width);
        expect_eq("spread3(3,1,2) lo", lo, 1);
        expect_eq("spread3(3,1,2) width", width, 2);
    }

    // Case 2: spread3(-4, 9, 1) -> lo=-4, width=13
    {
        int lo = 0, width = 0;
        asc::std::spread3(-4, 9, 1, lo, width);
        expect_eq("spread3(-4,9,1) lo", lo, -4);
        expect_eq("spread3(-4,9,1) width", width, 13);
    }

    // Case 3: spread3(7, 7, 7) -> lo=7, width=0
    {
        int lo = 0, width = 0;
        asc::std::spread3(7, 7, 7, lo, width);
        expect_eq("spread3(7,7,7) lo", lo, 7);
        expect_eq("spread3(7,7,7) width", width, 0);
    }

    // Case 4: floating point
    {
        float lo = 0.0f, width = 0.0f;
        asc::std::spread3(2.5f, -1.0f, 4.0f, lo, width);
        expect_eq("spread3(2.5f,-1.0f,4.0f) lo", lo, -1.0f);
        expect_eq("spread3(2.5f,-1.0f,4.0f) width", width, 5.0f);
    }

    // Case 5: negative range
    {
        int lo = 0, width = 0;
        asc::std::spread3(-10, -3, -7, lo, width);
        expect_eq("spread3(-10,-3,-7) lo", lo, -10);
        expect_eq("spread3(-10,-3,-7) width", width, 7);
    }

    return g_failures == 0 ? 0 : 1;
}
