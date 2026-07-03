#include "asc/std/__numeric/lcm.h"
#include <iostream>
#include <cstdint>
#include <climits>

static int g_failures = 0;

template <typename T>
static void expect_eq(const char* expr, T got, T expected)
{
    bool ok = (got == expected);
    std::cout << "[host][lcm] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

int main()
{
    // Basic cases from first CCCL test
    expect_eq("lcm(4, 6)",  asc::std::lcm(4, 6),  12);
    expect_eq("lcm(6, 4)",  asc::std::lcm(6, 4),  12);
    expect_eq("lcm(7, 13)", asc::std::lcm(7, 13), 91);   // coprime -> product
    expect_eq("lcm(3, 9)",  asc::std::lcm(3, 9),   9);   // multiple

    // Zero absorbs
    expect_eq("lcm(0, 5)", asc::std::lcm(0, 5), 0);
    expect_eq("lcm(5, 0)", asc::std::lcm(5, 0), 0);
    expect_eq("lcm(0, 0)", asc::std::lcm(0, 0), 0);

    // Sign-insensitive
    expect_eq("lcm(-4, 6)",  asc::std::lcm(-4, 6),  12);
    expect_eq("lcm(4, -6)",  asc::std::lcm(4, -6),  12);
    expect_eq("lcm(-4, -6)", asc::std::lcm(-4, -6), 12);

    // Additional cases from second CCCL test
    expect_eq("lcm(1, 1)",   asc::std::lcm(1, 1),   1);
    expect_eq("lcm(2, 3)",   asc::std::lcm(2, 3),   6);
    expect_eq("lcm(2, 4)",   asc::std::lcm(2, 4),   4);
    expect_eq("lcm(3, 17)",  asc::std::lcm(3, 17),  51);
    expect_eq("lcm(36, 18)", asc::std::lcm(36, 18), 36);

    // Sign-insensitive with additional cases
    expect_eq("lcm(-1, 0)",  asc::std::lcm(-1, 0),  0);
    expect_eq("lcm(0, -1)",  asc::std::lcm(0, -1),  0);
    expect_eq("lcm(-2, 3)",  asc::std::lcm(-2, 3),  6);
    expect_eq("lcm(-2, -3)", asc::std::lcm(-2, -3), 6);
    expect_eq("lcm(-36, 18)",  asc::std::lcm(-36, 18),  36);
    expect_eq("lcm(36, -18)",  asc::std::lcm(36, -18),  36);

    // Test with int64_t
    // GCD(1234, 5678) = 2, so LCM = (1234/2)*5678 = 617*5678 = 3503326
    expect_eq("lcm(int64_t(1234), int64_t(5678))",
              asc::std::lcm(static_cast<int64_t>(1234), static_cast<int64_t>(5678)),
              static_cast<int64_t>(3503326));

    // LWG#2837: lcm with large values (both args as int64_t)
    expect_eq("lcm(int64_t(1234), int64_t(INT32_MIN))",
              asc::std::lcm(static_cast<int64_t>(1234), static_cast<int64_t>(INT32_MIN)),
              static_cast<int64_t>(1324997410816LL));

    return g_failures == 0 ? 0 : 1;
}
