#include "asc/std/__ranges/from_range.h"
#include <iostream>
#include <type_traits>

static int g_failures = 0;

template <typename T>
static void expect_eq(const char* expr, T got, T expected)
{
    bool ok = (got == expected);
    std::cout << "[host][from_range] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

static void expect_true(const char* expr, bool cond)
{
    std::cout << "[host][from_range] " << expr << " = " << (cond ? "true" : "false")
              << " (expected true) " << (cond ? "OK" : "FAIL") << std::endl;
    if (!cond) ++g_failures;
}

int main()
{
    // 1. Type identity: from_range is of type from_range_t
    expect_true("is same type: from_range is from_range_t",
        std::is_same_v<decltype(asc::std::from_range), const asc::std::from_range_t>);

    // 2. Default constructible
    asc::std::from_range_t fr1{};
    (void)fr1;
    expect_true("from_range_t is default constructible", true);

    // 3. Copy constructible from the constexpr instance
    asc::std::from_range_t fr2 = asc::std::from_range;
    (void)fr2;
    expect_true("from_range_t is copy constructible from from_range", true);

    // 4. from_range usable as a tag argument
    auto take_tag = [](asc::std::from_range_t) { return 42; };
    expect_eq("from_range passed to function taking from_range_t", take_tag(asc::std::from_range), 42);

    // 5. sizeof is at least 1 (empty struct guarantee)
    expect_true("sizeof(from_range_t) >= 1", sizeof(asc::std::from_range_t) >= 1);

    // 6. from_range is constexpr and can be used at compile time
    constexpr asc::std::from_range_t fr3 = asc::std::from_range;
    (void)fr3;
    expect_true("from_range is constexpr-assignable", true);

    return g_failures == 0 ? 0 : 1;
}
