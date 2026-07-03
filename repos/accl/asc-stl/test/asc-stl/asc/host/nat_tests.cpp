#include "asc/std/__type_traits/nat.h"
#include <iostream>
#include <type_traits>

static int g_failures = 0;

static void expect_true(const char* expr, bool cond)
{
    std::cout << "[host][nat] " << expr << " = " << (cond ? "true" : "false")
              << " (expected true) " << (cond ? "OK" : "FAIL") << std::endl;
    if (!cond) ++g_failures;
}

static void expect_false(const char* expr, bool cond)
{
    std::cout << "[host][nat] " << expr << " = " << (cond ? "true" : "false")
              << " (expected false) " << (cond ? "FAIL" : "OK") << std::endl;
    if (cond) ++g_failures;
}

int main()
{
    using Nat = asc::std::__nat;

    // __nat is a struct (class) type
    expect_true("std::is_class<__nat>::value", std::is_class<Nat>::value);

    // Default constructor is deleted
    expect_false("std::is_default_constructible<__nat>::value", std::is_default_constructible<Nat>::value);

    // Copy constructor is deleted
    expect_false("std::is_copy_constructible<__nat>::value", std::is_copy_constructible<Nat>::value);

    // Copy assignment operator is deleted
    expect_false("std::is_copy_assignable<__nat>::value", std::is_copy_assignable<Nat>::value);

    // Destructor is deleted
    expect_false("std::is_destructible<__nat>::value", std::is_destructible<Nat>::value);

    // Move constructor is also deleted (implicitly suppressed by deleted copy)
    expect_false("std::is_move_constructible<__nat>::value", std::is_move_constructible<Nat>::value);

    // Move assignment is also deleted
    expect_false("std::is_move_assignable<__nat>::value", std::is_move_assignable<Nat>::value);

    return g_failures == 0 ? 0 : 1;
}
