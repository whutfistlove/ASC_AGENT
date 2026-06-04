// ACCL-side host test for min, migrated from the CCCL min test.
#include "ascend/std/__algorithm/min.h"
#include <iostream>

static int g_failures = 0;

template <typename T>
static void expect_eq(const char* expr, T got, T expected)
{
    bool ok = (got == expected);
    std::cout << "[host][min] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

int main()
{
    expect_eq("min(1, 2)", ascend::std::min(1, 2), 1);
    expect_eq("min(2, 1)", ascend::std::min(2, 1), 1);
    expect_eq("min(5.0f, 3.0f)", ascend::std::min(5.0f, 3.0f), 3.0f);
    expect_eq("min(-4, -9)", ascend::std::min(-4, -9), -9);

    auto comp = [](int a, int b) { return a < b; };
    expect_eq("min(10, 20, comp)", ascend::std::min(10, 20, comp), 10);
    expect_eq("min(20, 10, comp)", ascend::std::min(20, 10, comp), 10);

    return g_failures == 0 ? 0 : 1;
}
