#include "ascend/std/__algorithm/clamp.h"
#include <iostream>

static int g_failures = 0;

template <typename T>
static void expect_eq(const char* expr, T got, T expected)
{
    bool ok = (got == expected);
    std::cout << "[host][clamp] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

int main()
{
    expect_eq("clamp(5, 0, 10)", ascend::std::clamp(5, 0, 10), 5);
    expect_eq("clamp(-3, 0, 10)", ascend::std::clamp(-3, 0, 10), 0);
    expect_eq("clamp(42, 0, 10)", ascend::std::clamp(42, 0, 10), 10);
    expect_eq("clamp(2.5f, 1.0f, 2.0f)", ascend::std::clamp(2.5f, 1.0f, 2.0f), 2.0f);
    expect_eq("clamp(0, 0, 10)", ascend::std::clamp(0, 0, 10), 0);
    expect_eq("clamp(10, 0, 10)", ascend::std::clamp(10, 0, 10), 10);

    auto comp = [](int a, int b) { return a < b; };
    expect_eq("clamp(42, 0, 10, comp)", ascend::std::clamp(42, 0, 10, comp), 10);

    return g_failures == 0 ? 0 : 1;
}
