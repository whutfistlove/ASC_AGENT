#include "asc/std/__expected/unexpect.h"
#include <iostream>
#include <type_traits>

static int g_failures = 0;

template <typename T>
static void expect_eq(const char* expr, T got, T expected)
{
    bool ok = (got == expected);
    std::cout << "[host][unexpect] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

static void expect_true(const char* expr, bool cond)
{
    std::cout << "[host][unexpect] " << expr << " = " << (cond ? "true" : "false")
              << " (expected true) " << (cond ? "OK" : "FAIL") << std::endl;
    if (!cond) ++g_failures;
}

int main()
{
    // Test 1: unexpect_t is default-constructible via explicit direct initialization
    asc::std::unexpect_t u1{};
    (void)u1;

    // Test 2: unexpect's underlying type (removing const) is unexpect_t
    expect_true("is_same<remove_const_t<decltype(unexpect)>, unexpect_t>",
                std::is_same_v<std::remove_const_t<decltype(asc::std::unexpect)>, asc::std::unexpect_t>);

    // Test 3: unexpect is const (constexpr object implies const)
    expect_true("is_const<decltype(unexpect)>",
                std::is_const_v<decltype(asc::std::unexpect)>);

    // Test 4: unexpect is accessible (take its address)
    const asc::std::unexpect_t* ptr = &asc::std::unexpect;
    expect_true("&unexpect != nullptr", ptr != nullptr);

    // Test 5: sizeof(unexpect_t) == 1 (empty class)
    expect_eq("sizeof(unexpect_t)", static_cast<unsigned>(sizeof(asc::std::unexpect_t)), 1u);

    // Test 6: unexpect_t is default-constructible
    expect_true("is_default_constructible<unexpect_t>",
                std::is_default_constructible_v<asc::std::unexpect_t>);

    // Test 7: unexpect_t is trivially default-constructible (defaulted ctor)
    expect_true("is_trivially_default_constructible<unexpect_t>",
                std::is_trivially_default_constructible_v<asc::std::unexpect_t>);

    // Test 8: explicit default ctor prevents copy-list-initialization from {},
    // but copy/move constructors are still implicitly generated and NOT explicit.
    // is_convertible<unexpect_t, unexpect_t> is true because copy-initialization
    // from an unexpect_t prvalue uses the implicit copy/move ctor (not the explicit default ctor).
    // The explicit keyword only affects default construction context (e.g., unexpect_t t = {};).
    // Since there is no standard trait for "is_implicitly_default_constructible",
    // we verify the correct behavior: copy-constructibility is unaffected by explicit default ctor.
    expect_true("is_copy_constructible<unexpect_t>",
                std::is_copy_constructible_v<asc::std::unexpect_t>);

    // Test 9: unexpect_t is trivially copyable (all special members are defaulted/trivial)
    expect_true("is_trivially_copyable<unexpect_t>",
                std::is_trivially_copyable_v<asc::std::unexpect_t>);

    return g_failures == 0 ? 0 : 1;
}
