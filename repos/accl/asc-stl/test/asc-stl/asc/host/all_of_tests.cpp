#include "asc/std/__algorithm/all_of.h"

#include <iostream>

static int g_failures = 0;

template <typename T, int N, typename Predicate>
static bool independent_all_of(const T (&values)[N], Predicate pred)
{
    for (int i = 0; i < N; ++i)
    {
        if (!pred(values[i]))
        {
            return false;
        }
    }
    return true;
}

static void expect_bool(const char* expr, bool got, bool expected)
{
    std::cout << "[host][all_of] " << expr << " = " << (got ? "true" : "false")
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
    const int positive[] = {1, 2, 3, 4};
    const int mixed[] = {1, 0, 3, 4};
    const int evens[] = {2, 4, 6, 8};
    const int empty[] = {42};

    expect_bool(
        "all_of positive",
        asc::std::all_of(positive, positive + 4, IsPositive()),
        independent_all_of(positive, IsPositive()));
    expect_bool(
        "all_of mixed positive",
        asc::std::all_of(mixed, mixed + 4, IsPositive()),
        independent_all_of(mixed, IsPositive()));
    expect_bool(
        "all_of evens",
        asc::std::all_of(evens, evens + 4, IsEven()),
        independent_all_of(evens, IsEven()));
    expect_bool(
        "all_of empty range",
        asc::std::all_of(empty, empty, IsPositive()),
        true);

    constexpr int constexpr_values[] = {2, 4, 6};
    static_assert(asc::std::all_of(constexpr_values, constexpr_values + 3, IsEven()), "");

    return g_failures == 0 ? 0 : 1;
}
