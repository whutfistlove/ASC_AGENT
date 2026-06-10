#include "asc/std/__algorithm/sort3.h"
#include <iostream>

static int g_failures = 0;

template <typename T>
static void expect_eq(const char* expr, T got, T expected)
{
    bool ok = (got == expected);
    std::cout << "[host][sort3] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

int main()
{
    // already sorted
    {
        int lo = 0, mid = 0, hi = 0;
        asc::std::sort3(1, 2, 3, lo, mid, hi);
        expect_eq("sort3(1,2,3) lo", lo, 1);
        expect_eq("sort3(1,2,3) mid", mid, 2);
        expect_eq("sort3(1,2,3) hi", hi, 3);
    }

    // fully reversed
    {
        int lo = 0, mid = 0, hi = 0;
        asc::std::sort3(3, 2, 1, lo, mid, hi);
        expect_eq("sort3(3,2,1) lo", lo, 1);
        expect_eq("sort3(3,2,1) mid", mid, 2);
        expect_eq("sort3(3,2,1) hi", hi, 3);
    }

    // duplicates are preserved
    {
        int lo = 0, mid = 0, hi = 0;
        asc::std::sort3(5, 1, 5, lo, mid, hi);
        expect_eq("sort3(5,1,5) lo", lo, 1);
        expect_eq("sort3(5,1,5) mid", mid, 5);
        expect_eq("sort3(5,1,5) hi", hi, 5);
    }

    // negative values
    {
        int lo = 0, mid = 0, hi = 0;
        asc::std::sort3(-4, -9, -1, lo, mid, hi);
        expect_eq("sort3(-4,-9,-1) lo", lo, -9);
        expect_eq("sort3(-4,-9,-1) mid", mid, -4);
        expect_eq("sort3(-4,-9,-1) hi", hi, -1);
    }

    // floating point ordering
    {
        float lo = 0.0f, mid = 0.0f, hi = 0.0f;
        asc::std::sort3(2.5f, -1.0f, 0.5f, lo, mid, hi);
        expect_eq("sort3(2.5f,-1.0f,0.5f) lo", lo, -1.0f);
        expect_eq("sort3(2.5f,-1.0f,0.5f) mid", mid, 0.5f);
        expect_eq("sort3(2.5f,-1.0f,0.5f) hi", hi, 2.5f);
    }

    return g_failures == 0 ? 0 : 1;
}
