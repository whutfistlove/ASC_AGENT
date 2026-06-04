// ACCL-side host test for swap, migrated from the CCCL swap test.
//
// swap(a, b) is IN-PLACE and returns void. The migrated test exchanges two
// lvalues and checks that the values actually moved. It must NEVER be written
// as `auto out = ascend::std::swap(a, b)` — that would force a wrong, value
// returning signature onto the operator. The operator's CCCL semantics are
// ground truth; the test adapts to them, not the other way around.
#include "ascend/std/__algorithm/swap.h"
#include <iostream>

static int g_failures = 0;

template <typename T>
static void expect_eq(const char* expr, T got, T expected)
{
    bool ok = (got == expected);
    std::cout << "[host][swap] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

int main()
{
    int a = 1;
    int b = 2;
    ascend::std::swap(a, b);
    expect_eq("swap(a=1,b=2) -> a", a, 2);
    expect_eq("swap(a=1,b=2) -> b", b, 1);

    float x = 3.5f;
    float y = -1.0f;
    ascend::std::swap(x, y);
    expect_eq("swap(x=3.5,y=-1) -> x", x, -1.0f);
    expect_eq("swap(x=3.5,y=-1) -> y", y, 3.5f);

    return g_failures == 0 ? 0 : 1;
}
