#include "asc/std/__type_traits/integral_constant.h"
#include <iostream>
#include <type_traits>

static int g_failures = 0;

template <typename T>
static void expect_eq(const char* expr, T got, T expected)
{
    bool ok = (got == expected);
    std::cout << "[host][integral_constant] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

int main()
{
    // --- integral_constant<int, 42> ---
    using ic42 = asc::std::integral_constant<int, 42>;

    // value
    expect_eq("integral_constant<int,42>::value", ic42::value, 42);

    // value_type
    static_assert(std::is_same<ic42::value_type, int>::value, "value_type should be int");
    std::cout << "[host][integral_constant] integral_constant<int,42>::value_type is int OK" << std::endl;

    // type
    static_assert(std::is_same<ic42::type, ic42>::value, "type should be integral_constant<int,42>");
    std::cout << "[host][integral_constant] integral_constant<int,42>::type is integral_constant<int,42> OK" << std::endl;

    // implicit conversion operator
    ic42 ic;
    int converted = ic;
    expect_eq("integral_constant<int,42> implicit conversion", converted, 42);

    // call operator
    int called = ic();
    expect_eq("integral_constant<int,42>() call operator", called, 42);

    // --- true_type ---
    expect_eq("true_type::value", asc::std::true_type::value, true);
    asc::std::true_type tt;
    bool tt_converted = tt;
    expect_eq("true_type implicit conversion", tt_converted, true);
    bool tt_called = tt();
    expect_eq("true_type() call operator", tt_called, true);

    // --- false_type ---
    expect_eq("false_type::value", asc::std::false_type::value, false);
    asc::std::false_type ft;
    bool ft_converted = ft;
    expect_eq("false_type implicit conversion", ft_converted, false);
    bool ft_called = ft();
    expect_eq("false_type() call operator", ft_called, false);

    // --- bool_constant<true> ---
    using bc_true = asc::std::bool_constant<true>;
    expect_eq("bool_constant<true>::value", bc_true::value, true);
    static_assert(std::is_same<bc_true, asc::std::true_type>::value, "bool_constant<true> should be same as true_type");
    std::cout << "[host][integral_constant] bool_constant<true> is same as true_type OK" << std::endl;

    // --- bool_constant<false> ---
    using bc_false = asc::std::bool_constant<false>;
    expect_eq("bool_constant<false>::value", bc_false::value, false);
    static_assert(std::is_same<bc_false, asc::std::false_type>::value, "bool_constant<false> should be same as false_type");
    std::cout << "[host][integral_constant] bool_constant<false> is same as false_type OK" << std::endl;

    // --- integral_constant with other values ---
    using ic_zero = asc::std::integral_constant<int, 0>;
    expect_eq("integral_constant<int,0>::value", ic_zero::value, 0);

    using ic_neg = asc::std::integral_constant<int, -1>;
    expect_eq("integral_constant<int,-1>::value", ic_neg::value, -1);

    using ic_large = asc::std::integral_constant<unsigned, 1000u>;
    expect_eq("integral_constant<unsigned,1000>::value", ic_large::value, 1000u);

    return g_failures == 0 ? 0 : 1;
}
