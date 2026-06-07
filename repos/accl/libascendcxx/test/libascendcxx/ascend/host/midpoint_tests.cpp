#include "ascend/std/numeric"
#include <cmath>
#include <cstdint>
#include <iostream>
#include <limits>
#include <type_traits>

static int g_failures = 0;

template <class T>
constexpr T midpoint_integral_ref(T a, T b)
{
    const __int128 wide_a = static_cast<__int128>(a);
    const __int128 wide_b = static_cast<__int128>(b);
    return static_cast<T>(wide_a + (wide_b - wide_a) / 2);
}

template <class T>
void expect_eq(const char* label, T got, T expected)
{
    if (got != expected) {
        ++g_failures;
        std::cout << "[host][midpoint] FAIL " << label << std::endl;
    }
}

template <class T>
void expect_near(const char* label, T got, T expected, T eps)
{
    if (std::fabs(got - expected) > eps) {
        ++g_failures;
        std::cout << "[host][midpoint] FAIL " << label << std::endl;
    }
}

template <class T>
void check_integral()
{
    static_assert(std::is_same<T, decltype(ascend::std::midpoint(T(), T()))>::value, "");
    static_assert(noexcept(ascend::std::midpoint(T(), T())), "");

    expect_eq("1,3", ascend::std::midpoint(T(1), T(3)), midpoint_integral_ref(T(1), T(3)));
    expect_eq("3,1", ascend::std::midpoint(T(3), T(1)), midpoint_integral_ref(T(3), T(1)));
    expect_eq("1,4", ascend::std::midpoint(T(1), T(4)), midpoint_integral_ref(T(1), T(4)));
    expect_eq("4,1", ascend::std::midpoint(T(4), T(1)), midpoint_integral_ref(T(4), T(1)));

    if constexpr (std::is_signed<T>::value) {
        expect_eq("-3,4", ascend::std::midpoint(T(-3), T(4)), midpoint_integral_ref(T(-3), T(4)));
        expect_eq("4,-3", ascend::std::midpoint(T(4), T(-3)), midpoint_integral_ref(T(4), T(-3)));
        expect_eq("min,max",
                  ascend::std::midpoint((std::numeric_limits<T>::min)(), (std::numeric_limits<T>::max)()),
                  midpoint_integral_ref((std::numeric_limits<T>::min)(), (std::numeric_limits<T>::max)()));
        expect_eq("max,min",
                  ascend::std::midpoint((std::numeric_limits<T>::max)(), (std::numeric_limits<T>::min)()),
                  midpoint_integral_ref((std::numeric_limits<T>::max)(), (std::numeric_limits<T>::min)()));
    } else {
        expect_eq("0,max",
                  ascend::std::midpoint(T(0), (std::numeric_limits<T>::max)()),
                  midpoint_integral_ref(T(0), (std::numeric_limits<T>::max)()));
        expect_eq("max,0",
                  ascend::std::midpoint((std::numeric_limits<T>::max)(), T(0)),
                  midpoint_integral_ref((std::numeric_limits<T>::max)(), T(0)));
    }
}

template <class T>
void check_floating(T eps)
{
    static_assert(std::is_same<T, decltype(ascend::std::midpoint(T(), T()))>::value, "");
    static_assert(noexcept(ascend::std::midpoint(T(), T())), "");

    expect_eq("0,0", ascend::std::midpoint(T(0), T(0)), T(0));
    expect_eq("2,4", ascend::std::midpoint(T(2), T(4)), T(3));
    expect_eq("3,4", ascend::std::midpoint(T(3), T(4)), T(3.5));
    expect_near("1.3,11.4", ascend::std::midpoint(T(1.3), T(11.4)), T(6.35), eps);
    expect_near("-1.3,11.4", ascend::std::midpoint(T(-1.3), T(11.4)), T(5.05), eps);
    expect_near("max,0",
                ascend::std::midpoint((std::numeric_limits<T>::max)(), T(0)),
                (std::numeric_limits<T>::max)() / T(2),
                eps * (std::numeric_limits<T>::max)());
}

int main()
{
    check_integral<signed char>();
    check_integral<short>();
    check_integral<int>();
    check_integral<long>();
    check_integral<long long>();
    check_integral<std::int8_t>();
    check_integral<std::int16_t>();
    check_integral<std::int32_t>();
    check_integral<std::int64_t>();
    check_integral<unsigned char>();
    check_integral<unsigned short>();
    check_integral<unsigned int>();
    check_integral<unsigned long>();
    check_integral<unsigned long long>();
    check_integral<std::uint8_t>();
    check_integral<std::uint16_t>();
    check_integral<std::uint32_t>();
    check_integral<std::uint64_t>();

    check_floating<float>(1.0e-4f);
    check_floating<double>(1.0e-12);

    int data[] = {0, 1, 2, 3, 4, 5};
    expect_eq("ptr 0,4", ascend::std::midpoint(data, data + 4), data + 2);
    expect_eq("ptr 5,1", ascend::std::midpoint(data + 5, data + 1), data + 3);

    constexpr int c = ascend::std::midpoint((std::numeric_limits<int>::min)(), (std::numeric_limits<int>::max)());
    static_assert(c == -1, "");

    return g_failures == 0 ? 0 : 1;
}
