// ACCL-side host test for minmax, migrated from the CCCL minmax test.
//
// minmax returns a pair<const T&, const T&> {min, max}.
// We check both .first and .second against INDEPENDENT expected values.
#include "ascend/std/__algorithm/minmax.h"
#include <iostream>

static int g_failures = 0;

template <typename T>
static void expect_eq(const char* expr, T got, T expected)
{
    bool ok = (got == expected);
    std::cout << "[host][minmax] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

int main()
{
    // minmax(3, 8) -> {3, 8}
    {
        auto pr = ascend::std::minmax(3, 8);
        expect_eq("minmax(3, 8).first", pr.first, 3);
        expect_eq("minmax(3, 8).second", pr.second, 8);
    }
    // minmax(8, 3) -> {3, 8}
    {
        auto pr = ascend::std::minmax(8, 3);
        expect_eq("minmax(8, 3).first", pr.first, 3);
        expect_eq("minmax(8, 3).second", pr.second, 8);
    }
    // minmax(5, 5) -> {5, 5} (equal: ties keep order {a, b})
    {
        auto pr = ascend::std::minmax(5, 5);
        expect_eq("minmax(5, 5).first", pr.first, 5);
        expect_eq("minmax(5, 5).second", pr.second, 5);
    }
    // Custom comparator (operator< wrapped in lambda)
    {
        auto comp = [](int a, int b) { return a < b; };
        auto pr = ascend::std::minmax(8, 3, comp);
        expect_eq("minmax(8, 3, comp).first", pr.first, 3);
        expect_eq("minmax(8, 3, comp).second", pr.second, 8);
    }
    // Float values
    {
        auto pr = ascend::std::minmax(5.0f, 3.0f);
        expect_eq("minmax(5.0f, 3.0f).first", pr.first, 3.0f);
        expect_eq("minmax(5.0f, 3.0f).second", pr.second, 5.0f);
    }
    // Negative values
    {
        auto pr = ascend::std::minmax(-4, -9);
        expect_eq("minmax(-4, -9).first", pr.first, -9);
        expect_eq("minmax(-4, -9).second", pr.second, -4);
    }

    return g_failures == 0 ? 0 : 1;
}
