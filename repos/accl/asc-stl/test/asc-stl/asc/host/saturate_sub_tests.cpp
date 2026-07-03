#include "asc/std/__numeric/saturate_sub.h"
#include <iostream>

static int g_failures = 0;

template <typename T>
static void expect_eq(const char* expr, T got, T expected)
{
    bool ok = (got == expected);
    std::cout << "[host][saturate_sub] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

int main()
{
    // Integer cases from CCCL test
    expect_eq("saturate_sub(5, 2)", asc::std::saturate_sub(5, 2), 3);
    expect_eq("saturate_sub(2, 5)", asc::std::saturate_sub(2, 5), 0);   // saturates at zero
    expect_eq("saturate_sub(7, 7)", asc::std::saturate_sub(7, 7), 0);
    expect_eq("saturate_sub(10, 0)", asc::std::saturate_sub(10, 0), 10);

    // Float cases from CCCL test
    expect_eq("saturate_sub(2.5f, 1.0f)", asc::std::saturate_sub(2.5f, 1.0f), 1.5f);
    expect_eq("saturate_sub(1.0f, 2.5f)", asc::std::saturate_sub(1.0f, 2.5f), 0.0f);

    return g_failures == 0 ? 0 : 1;
}
