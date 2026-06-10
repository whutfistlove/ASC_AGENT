#include "asc/std/numeric"
#include <cstdint>
#include <iostream>
#include <limits>
#include <type_traits>

static int g_failures = 0;

template <class Rp, class Tp>
constexpr typename std::make_unsigned<Rp>::type abs_to_unsigned_ref(Tp value)
{
    using Up = typename std::make_unsigned<Rp>::type;
    if constexpr (std::is_signed<Tp>::value) {
        return value < 0 ? static_cast<Up>(Up(0) - static_cast<Up>(value)) : static_cast<Up>(value);
    } else {
        return static_cast<Up>(value);
    }
}

template <class Tp, class Up>
constexpr typename std::common_type<Tp, Up>::type gcd_ref(Tp lhs, Up rhs)
{
    using Rp = typename std::common_type<Tp, Up>::type;
    using Wp = typename std::make_unsigned<Rp>::type;
    Wp a = abs_to_unsigned_ref<Rp>(lhs);
    Wp b = abs_to_unsigned_ref<Rp>(rhs);
    while (b != 0) {
        Wp t = static_cast<Wp>(a % b);
        a = b;
        b = t;
    }
    return static_cast<Rp>(a);
}

template <class Expected, class Actual>
void expect_eq(const char* label, Actual got, Expected expected)
{
    if (got != static_cast<Actual>(expected)) {
        ++g_failures;
        std::cout << "[host][gcd] FAIL " << label << std::endl;
    }
}

template <class A, class B>
void check_pair(A a, B b)
{
    using ExpectedType = typename std::common_type<A, B>::type;
    static_assert(std::is_same<ExpectedType, decltype(asc::std::gcd(a, b))>::value, "");
    const ExpectedType expected = gcd_ref(a, b);
    expect_eq("gcd(a,b)", asc::std::gcd(a, b), expected);
    expect_eq("gcd(b,a)", asc::std::gcd(b, a), gcd_ref(b, a));
}

int main()
{
    check_pair(0, 0);
    check_pair(1, 0);
    check_pair(0, 1);
    check_pair(2, 3);
    check_pair(2, 4);
    check_pair(36, 18);
    check_pair(-36, 18);
    check_pair(36, -18);
    check_pair(-36, -18);
    check_pair(static_cast<signed char>(36), static_cast<short>(18));
    check_pair(static_cast<std::int8_t>(36), static_cast<std::int64_t>(18));
    check_pair(static_cast<unsigned int>(36), static_cast<unsigned long>(18));
    check_pair(-36, static_cast<unsigned int>(18));
    check_pair(static_cast<std::int64_t>(1234), static_cast<std::int32_t>((std::numeric_limits<std::int32_t>::min)()));

    constexpr auto c = asc::std::gcd(48, -18);
    static_assert(c == 6, "");

    return g_failures == 0 ? 0 : 1;
}
