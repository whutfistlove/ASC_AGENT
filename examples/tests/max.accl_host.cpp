// ACCL-side host test for max, migrated from the CCCL max test.
//
// Conventions every migrated host test MUST follow:
//   * include the migrated ACCL header by its repo-relative path;
//   * print EACH case with its actual values via expect_eq(...);
//   * return 0 only if every case passed, non-zero otherwise (so ctest fails).
//
// max is a binary value-returning op, so we compare the result to an
// INDEPENDENT expected value (a literal here), never to ascend::std::max again.
#include "ascend/std/__algorithm/max.h"
#include <iostream>

static int g_failures = 0;

template <typename T>
static void expect_eq(const char* expr, T got, T expected)
{
    bool ok = (got == expected);
    std::cout << "[host][max] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

int main()
{
    expect_eq("max(1, 2)", ascend::std::max(1, 2), 2);
    expect_eq("max(2, 1)", ascend::std::max(2, 1), 2);
    expect_eq("max(5.0f, 3.0f)", ascend::std::max(5.0f, 3.0f), 5.0f);

    auto comp = [](int a, int b) { return a < b; };
    expect_eq("max(10, 20, comp)", ascend::std::max(10, 20, comp), 20);

    return g_failures == 0 ? 0 : 1;
}
