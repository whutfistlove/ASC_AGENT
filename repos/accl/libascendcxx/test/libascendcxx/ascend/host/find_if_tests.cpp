#include "ascend/std/__algorithm/find_if.h"

#include <cstddef>
#include <iostream>

static int g_failures = 0;

template <typename T, typename Predicate>
static const T* independent_find_if(const T* first, const T* last, Predicate pred)
{
    for (; first != last; ++first)
    {
        if (pred(*first))
        {
            return first;
        }
    }
    return last;
}

static void expect_index(const char* expr, const int* got, const int* first, const int* expected)
{
    const std::ptrdiff_t got_index = got - first;
    const std::ptrdiff_t expected_index = expected - first;
    std::cout << "[host][find_if] " << expr << " = " << got_index
              << " (expected " << expected_index << ") "
              << (got == expected ? "OK" : "FAIL") << std::endl;
    if (got != expected)
    {
        ++g_failures;
    }
}

struct Equals {
    int value;

    constexpr bool operator()(int other) const
    {
        return other == value;
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
    const int values[] = {2, 4, 6, 8};
    const int repeated[] = {1, 4, 4, 8};
    const int odds[] = {1, 3, 5, 7};

    expect_index(
        "first element matches",
        ascend::std::find_if(values, values + 4, Equals{2}),
        values,
        independent_find_if(values, values + 4, Equals{2}));
    expect_index(
        "middle element matches",
        ascend::std::find_if(values, values + 4, Equals{6}),
        values,
        independent_find_if(values, values + 4, Equals{6}));
    expect_index(
        "last element matches",
        ascend::std::find_if(values, values + 4, Equals{8}),
        values,
        independent_find_if(values, values + 4, Equals{8}));
    expect_index(
        "first repeated match",
        ascend::std::find_if(repeated, repeated + 4, Equals{4}),
        repeated,
        independent_find_if(repeated, repeated + 4, Equals{4}));
    expect_index(
        "no element matches",
        ascend::std::find_if(values, values + 4, Equals{10}),
        values,
        independent_find_if(values, values + 4, Equals{10}));
    expect_index(
        "empty range",
        ascend::std::find_if(values, values, IsEven()),
        values,
        values);
    expect_index(
        "odds even",
        ascend::std::find_if(odds, odds + 4, IsEven()),
        odds,
        independent_find_if(odds, odds + 4, IsEven()));

    constexpr int constexpr_values[] = {1, 3, 4, 7};
    static_assert(ascend::std::find_if(constexpr_values, constexpr_values + 4, IsEven()) == constexpr_values + 2, "");

    return g_failures == 0 ? 0 : 1;
}
