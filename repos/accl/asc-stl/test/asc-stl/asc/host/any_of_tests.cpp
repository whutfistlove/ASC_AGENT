#include "asc/std/__algorithm/any_of.h"

#include <iostream>

static int g_failures = 0;

template <typename T, int N, typename Predicate>
static bool independent_any_of(const T (&values)[N], Predicate pred)
{
    for (int i = 0; i < N; ++i)
    {
        if (pred(values[i]))
        {
            return true;
        }
    }
    return false;
}

static void expect_bool(const char* expr, bool got, bool expected)
{
    std::cout << "[host][any_of] " << expr << " = " << (got ? "true" : "false")
              << " (expected " << (expected ? "true" : "false") << ") "
              << (got == expected ? "OK" : "FAIL") << std::endl;
    if (got != expected)
    {
        ++g_failures;
    }
}

struct IsPositive {
    constexpr bool operator()(int value) const
    {
        return value > 0;
    }
};

struct IsEven {
    constexpr bool operator()(int value) const
    {
        return (value % 2) == 0;
    }
};

int main()
{
    const int evens[] = {2, 4, 6, 8};
    const int mixed[] = {1, 3, 6, 7};
    const int odds[] = {1, 3, 5, 7};
    const int negative[] = {-4, -3, -2, -1};
    const int empty[] = {42};

    expect_bool(
        "any_of evens",
        asc::std::any_of(evens, evens + 4, IsEven()),
        independent_any_of(evens, IsEven()));
    expect_bool(
        "any_of mixed even",
        asc::std::any_of(mixed, mixed + 4, IsEven()),
        independent_any_of(mixed, IsEven()));
    expect_bool(
        "any_of odds even",
        asc::std::any_of(odds, odds + 4, IsEven()),
        independent_any_of(odds, IsEven()));
    expect_bool(
        "any_of negative positive",
        asc::std::any_of(negative, negative + 4, IsPositive()),
        independent_any_of(negative, IsPositive()));
    expect_bool(
        "any_of empty range",
        asc::std::any_of(empty, empty, IsEven()),
        false);

    constexpr int constexpr_values[] = {1, 3, 4, 7};
    static_assert(asc::std::any_of(constexpr_values, constexpr_values + 4, IsEven()), "");

    return g_failures == 0 ? 0 : 1;
}
