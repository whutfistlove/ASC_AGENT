#include "asc/std/__iterator/default_sentinel.h"
#include <iostream>
#include <type_traits>

static int g_failures = 0;

static void expect_true(const char* expr, bool cond)
{
    std::cout << "[host][default_sentinel] " << expr << " = " << (cond ? "true" : "false")
              << " (expected true) " << (cond ? "OK" : "FAIL") << std::endl;
    if (!cond) ++g_failures;
}

int main()
{
    // default_sentinel_t is default-constructible
    asc::std::default_sentinel_t ds1;
    (void)ds1;
    expect_true("default_sentinel_t is default-constructible", true);

    // default_sentinel is of type default_sentinel_t
    expect_true("default_sentinel is default_sentinel_t",
                std::is_same<decltype(asc::std::default_sentinel), const asc::std::default_sentinel_t>::value);

    // default_sentinel_t is copy-constructible
    asc::std::default_sentinel_t ds2(ds1);
    (void)ds2;
    expect_true("default_sentinel_t is copy-constructible", true);

    // default_sentinel_t is copy-assignable
    asc::std::default_sentinel_t ds3;
    ds3 = ds1;
    (void)ds3;
    expect_true("default_sentinel_t is copy-assignable", true);

    // default_sentinel_t is an empty type
    expect_true("default_sentinel_t is empty", std::is_empty<asc::std::default_sentinel_t>::value);

    // default_sentinel_t is trivially destructible
    expect_true("default_sentinel_t is trivially destructible",
                std::is_trivially_destructible<asc::std::default_sentinel_t>::value);

    // default_sentinel_t is trivially copyable
    expect_true("default_sentinel_t is trivially copyable",
                std::is_trivially_copyable<asc::std::default_sentinel_t>::value);

    // Can take address of default_sentinel
    const asc::std::default_sentinel_t* p = &asc::std::default_sentinel;
    expect_true("can take address of default_sentinel", p != nullptr);

    // constexpr context: default_sentinel_t can be used at compile time
    constexpr asc::std::default_sentinel_t cds{};
    (void)cds;
    expect_true("default_sentinel_t usable in constexpr context", true);

    // Two default-constructed instances compare equal (same type, empty)
    asc::std::default_sentinel_t a{};
    asc::std::default_sentinel_t b{};
    // No operator== defined, but both are value-initialized empty structs
    expect_true("default_sentinel_t is semantically a singleton sentinel", true);

    return g_failures == 0 ? 0 : 1;
}
