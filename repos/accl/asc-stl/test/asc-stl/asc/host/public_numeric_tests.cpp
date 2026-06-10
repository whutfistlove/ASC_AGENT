#include "asc/std/numeric"

#include <cstdint>
#include <iostream>
#include <limits>

constexpr int abs_ref(int value)
{
    return value < 0 ? -value : value;
}

constexpr int gcd_ref(int lhs, int rhs)
{
    int a = abs_ref(lhs);
    int b = abs_ref(rhs);
    while (b != 0) {
        int next = a % b;
        a = b;
        b = next;
    }
    return a;
}

constexpr int lcm_ref(int lhs, int rhs)
{
    return lhs == 0 || rhs == 0 ? 0 : abs_ref((lhs / gcd_ref(lhs, rhs)) * rhs);
}

constexpr int midpoint_ref(int lhs, int rhs)
{
    return static_cast<int>(static_cast<std::int64_t>(lhs) + (static_cast<std::int64_t>(rhs) - lhs) / 2);
}

int main()
{
    int failures = 0;

    if (asc::std::gcd(-48, 18) != gcd_ref(-48, 18)) {
        ++failures;
        std::cout << "[host][public_numeric] gcd failed" << std::endl;
    }
    if (asc::std::lcm(-12, 18) != lcm_ref(-12, 18)) {
        ++failures;
        std::cout << "[host][public_numeric] lcm failed" << std::endl;
    }
    if (asc::std::midpoint(3, 8) != midpoint_ref(3, 8)) {
        ++failures;
        std::cout << "[host][public_numeric] midpoint odd failed" << std::endl;
    }
    if (asc::std::midpoint((std::numeric_limits<int>::min)(), (std::numeric_limits<int>::max)()) !=
        midpoint_ref((std::numeric_limits<int>::min)(), (std::numeric_limits<int>::max)())) {
        ++failures;
        std::cout << "[host][public_numeric] midpoint range failed" << std::endl;
    }

    int values[4] = {1, 2, 3, 4};
    if (asc::std::midpoint(values, values + 4) != values + 2) {
        ++failures;
        std::cout << "[host][public_numeric] pointer midpoint failed" << std::endl;
    }

    constexpr int cgcd = asc::std::gcd(84, 30);
    constexpr int clcm = asc::std::lcm(12, 18);
    constexpr int cmid = asc::std::midpoint(10, 20);
    static_assert(cgcd == 6, "");
    static_assert(clcm == 36, "");
    static_assert(cmid == 15, "");

    return failures == 0 ? 0 : 1;
}
