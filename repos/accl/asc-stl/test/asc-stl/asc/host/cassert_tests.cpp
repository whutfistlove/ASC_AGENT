#include "asc/std/cassert"
#include <iostream>

static int g_failures = 0;

template <typename T>
static void expect_eq(const char* expr, T got, T expected)
{
    bool ok = (got == expected);
    std::cout << "[host][cassert] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

static void expect_true(const char* expr, bool cond)
{
    std::cout << "[host][cassert] " << expr << " = " << (cond ? "true" : "false")
              << " (expected true) " << (cond ? "OK" : "FAIL") << std::endl;
    if (!cond) ++g_failures;
}

int main()
{
    // Test 1: assert(true) should not abort — if we reach here, the include worked
    // and the assert macro is functional.
    assert(true);
    expect_true("assert(true) did not abort", true);

    // Test 2: assert with a non-trivial true expression
    int x = 42;
    assert(x == 42);
    expect_true("assert(x == 42) did not abort", true);

    // Test 3: assert with a comparison expression
    int a = 10, b = 20;
    assert(a < b);
    expect_true("assert(a < b) did not abort", true);

    // Test 4: assert with a side-effect expression — verify program continues
    int counter = 0;
    assert((++counter, true));
    expect_true("assert with side-effect did not abort", true);

    // Test 5: assert in a constexpr-friendly context
    constexpr int ci = 5;
    assert(ci == 5);
    expect_eq("ci", ci, 5);

    // Test 6: The header provides the standard assert macro — verify it's a macro
#ifdef assert
    expect_true("assert is defined as a macro", true);
#else
    expect_true("assert is defined as a macro", false);
#endif

    // Test 7: assert with pointer comparison
    int arr[3] = {1, 2, 3};
    assert(arr != nullptr);
    expect_true("assert(arr != nullptr) did not abort", true);

    // Test 8: assert with boolean expression
    assert(true && true);
    expect_true("assert(true && true) did not abort", true);

    return g_failures == 0 ? 0 : 1;
}
