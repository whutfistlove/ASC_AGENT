#include "asc/std/__utility/undefined.h"
#include <iostream>
#include <type_traits>

static int g_failures = 0;

static void expect_true(const char* expr, bool cond)
{
    std::cout << "[host][undefined] " << expr << " = " << (cond ? "true" : "false")
              << " (expected true) " << (cond ? "OK" : "FAIL") << std::endl;
    if (!cond) ++g_failures;
}

// SFINAE test: detect whether a type is complete (has a definition)
template <typename T, typename = void>
struct is_complete : std::false_type {};

template <typename T>
struct is_complete<T, std::void_t<decltype(sizeof(T))>> : std::true_type {};

int main()
{
    // __undefined<int> should be incomplete (deliberately undefined)
    expect_true("is_complete<__undefined<int>>::value == false",
                is_complete<asc::std::__undefined<int>>::value == false);

    // __undefined<> (zero args) should also be incomplete
    expect_true("is_complete<__undefined<>>::value == false",
                is_complete<asc::std::__undefined<>>::value == false);

    // __undefined<int, float> (multiple args) should also be incomplete
    expect_true("is_complete<__undefined<int, float>>::value == false",
                is_complete<asc::std::__undefined<int, float>>::value == false);

    // Can form pointers to incomplete types (compile check)
    expect_true("pointer to __undefined<int> is not void",
                !std::is_same_v<asc::std::__undefined<int>*, void>);

    // Can form references to incomplete types (compile check)
    expect_true("reference to __undefined<int> is not void",
                !std::is_same_v<asc::std::__undefined<int>&, void>);

    // Sanity: int should be complete
    expect_true("is_complete<int>::value == true (sanity)",
                is_complete<int>::value == true);

    return g_failures == 0 ? 0 : 1;
}
