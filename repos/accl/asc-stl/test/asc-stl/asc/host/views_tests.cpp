#include "asc/std/__ranges/views.h"
#include <iostream>

static int g_failures = 0;

template <typename T>
static void expect_eq(const char* expr, T got, T expected)
{
    bool ok = (got == expected);
    std::cout << "[host][views] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

int main()
{
    // The views header is currently a stub: namespace views alias is commented out
    // (TODO: Uncomment once asc::std::ranges::views namespace is defined).
    // There are no callable entities to test at this time.
    // This test verifies the header compiles and includes without error.
    expect_eq("1 + 1 (header compiles)", 1 + 1, 2);
    std::cout << "[host][views] Header inclusion OK (stub - no active symbols to test)" << std::endl;
    return g_failures == 0 ? 0 : 1;
}
