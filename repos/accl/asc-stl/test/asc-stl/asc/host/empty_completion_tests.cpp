#include "asc/std/__barrier/empty_completion.h"
#include <iostream>
#include <type_traits>

static int g_failures = 0;

static void expect_true(const char* expr, bool cond)
{
    std::cout << "[host][empty_completion] " << expr << " = " << (cond ? "true" : "false")
              << " (expected true) " << (cond ? "OK" : "FAIL") << std::endl;
    if (!cond) ++g_failures;
}

int main()
{
    // Test default construction
    asc::std::__empty_completion ec;

    // Test that operator() is callable and returns void
    ec();

    // Test noexcept
    expect_true("noexcept(asc::std::__empty_completion{}())", noexcept(asc::std::__empty_completion{}()));

    // Test constexpr usage — comma operator: call void function, evaluate to true
    constexpr bool can_call_constexpr = (asc::std::__empty_completion{}(), true);
    expect_true("constexpr callable", can_call_constexpr);

    // Test that calling multiple times is fine
    ec();
    ec();

    // Verify the type has a valid size (trivial struct with no data members)
    expect_true("sizeof(__empty_completion) > 0", sizeof(asc::std::__empty_completion) > 0);

    // Verify operator() returns void
    expect_true("returns void", std::is_same_v<decltype(asc::std::__empty_completion{}()), void>);

    return g_failures == 0 ? 0 : 1;
}
