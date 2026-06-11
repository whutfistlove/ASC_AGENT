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

static void expect_true(const char* expr, bool cond)
{
    std::cout << "[host][integral_constant] " << expr << " = " << (cond ? "true" : "false")
              << " (expected true) " << (cond ? "OK" : "FAIL") << std::endl;
    if (!cond) ++g_failures;
}

int main()
{
    // --- integral_constant<int, 42> ---
    {
        using IC = asc::std::integral_constant<int, 42>;
        expect_eq("integral_constant<int,42>::value", IC::value, 42);
        expect_true("value_type is int", std::is_same<IC::value_type, int>::value);
        expect_true("type is integral_constant<int,42>", std::is_same<IC::type, IC>::value);

        IC ic{};
        expect_eq("implicit conversion to int", static_cast<int>(ic), 42);
        expect_eq("call operator", ic(), 42);
    }

    // --- integral_constant<unsigned, 0> ---
    {
        using IC = asc::std::integral_constant<unsigned, 0>;
        expect_eq("integral_constant<unsigned,0>::value", IC::value, 0u);
        expect_true("value_type is unsigned", std::is_same<IC::value_type, unsigned>::value);

        IC ic{};
        expect_eq("implicit conversion to unsigned", static_cast<unsigned>(ic), 0u);
        expect_eq("call operator", ic(), 0u);
    }

    // --- true_type ---
    {
        expect_eq("true_type::value", asc::std::true_type::value, true);
        expect_true("true_type::value_type is bool",
                     std::is_same<asc::std::true_type::value_type, bool>::value);

        asc::std::true_type tt{};
        expect_eq("true_type implicit conversion", static_cast<bool>(tt), true);
        expect_eq("true_type call operator", tt(), true);
    }

    // --- false_type ---
    {
        expect_eq("false_type::value", asc::std::false_type::value, false);

        asc::std::false_type ft{};
        expect_eq("false_type implicit conversion", static_cast<bool>(ft), false);
        expect_eq("false_type call operator", ft(), false);
    }

    // --- bool_constant<true> ---
    {
        using BT = asc::std::bool_constant<true>;
        expect_eq("bool_constant<true>::value", BT::value, true);
        expect_true("bool_constant<true> is same as true_type",
                     std::is_same<BT, asc::std::true_type>::value);
    }

    // --- bool_constant<false> ---
    {
        using BF = asc::std::bool_constant<false>;
        expect_eq("bool_constant<false>::value", BF::value, false);
        expect_true("bool_constant<false> is same as false_type",
                     std::is_same<BF, asc::std::false_type>::value);
    }

    // --- negative value ---
    {
        using IC = asc::std::integral_constant<int, -1>;
        expect_eq("integral_constant<int,-1>::value", IC::value, -1);
        IC ic{};
        expect_eq("integral_constant<int,-1> call operator", ic(), -1);
    }

    // --- large value ---
    {
        using IC = asc::std::integral_constant<long long, 1000000000000LL>;
        expect_eq("integral_constant<long long,1e12>::value", IC::value, 1000000000000LL);
    }

    return g_failures == 0 ? 0 : 1;
}
