// ACCL-side host test for gcd, migrated from CCCL __numeric/gcd.pass.cpp
// and numerics/numeric.ops/numeric.ops.gcd/gcd.pass.cpp.
//
// gcd is a binary value-returning integer op: template<typename T> T gcd(T, T).
// Result is always non-negative; sign of inputs does not matter.
// The test compares the result to an INDEPENDENT expected value.
#include "asc/std/__numeric/gcd.h"
#include <iostream>
#include <cstdint>
#include <climits>

static int g_failures = 0;

template <typename T>
static void expect_eq(const char* expr, T got, T expected)
{
    bool ok = (got == expected);
    std::cout << "[host][gcd] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

int main()
{
    // ---- Basic cases (from CCCL __numeric/gcd.pass.cpp) ----
    expect_eq("gcd(12, 18)",  asc::std::gcd(12, 18),  6);
    expect_eq("gcd(18, 12)",  asc::std::gcd(18, 12),  6);
    expect_eq("gcd(48, 36)",  asc::std::gcd(48, 36),  12);
    expect_eq("gcd(7, 13)",   asc::std::gcd(7, 13),   1);   // coprime

    // ---- Zero and identity behaviour ----
    expect_eq("gcd(0, 5)",    asc::std::gcd(0, 5),    5);
    expect_eq("gcd(5, 0)",    asc::std::gcd(5, 0),    5);
    expect_eq("gcd(0, 0)",    asc::std::gcd(0, 0),    0);

    // ---- Sign-insensitive ----
    expect_eq("gcd(-12, 18)",  asc::std::gcd(-12, 18),  6);
    expect_eq("gcd(12, -18)",  asc::std::gcd(12, -18),  6);
    expect_eq("gcd(-12, -18)", asc::std::gcd(-12, -18), 6);

    // ---- Additional cases from second CCCL test (same-type int) ----
    expect_eq("gcd(1, 0)",    asc::std::gcd(1, 0),    1);
    expect_eq("gcd(0, 1)",    asc::std::gcd(0, 1),    1);
    expect_eq("gcd(1, 1)",    asc::std::gcd(1, 1),    1);
    expect_eq("gcd(2, 3)",    asc::std::gcd(2, 3),    1);
    expect_eq("gcd(2, 4)",    asc::std::gcd(2, 4),    2);
    expect_eq("gcd(36, 17)",  asc::std::gcd(36, 17),  1);
    expect_eq("gcd(36, 18)",  asc::std::gcd(36, 18),  18);

    // ---- Sign-insensitive with more cases ----
    expect_eq("gcd(-1, 0)",   asc::std::gcd(-1, 0),   1);
    expect_eq("gcd(0, -1)",   asc::std::gcd(0, -1),   1);
    expect_eq("gcd(-2, -4)",  asc::std::gcd(-2, -4),  2);
    expect_eq("gcd(-36, 18)", asc::std::gcd(-36, 18), 18);
    expect_eq("gcd(36, -18)", asc::std::gcd(36, -18), 18);

    // ---- int64_t cases ----
    expect_eq("gcd(int64_t(1234), int64_t(5678))",
              asc::std::gcd(static_cast<int64_t>(1234), static_cast<int64_t>(5678)),
              static_cast<int64_t>(2));

    // LWG#2837: gcd(1234, INT32_MIN) == 2  (INT32_MIN = -2147483648)
    expect_eq("gcd(int64_t(1234), int64_t(INT32_MIN))",
              asc::std::gcd(static_cast<int64_t>(1234), static_cast<int64_t>(INT32_MIN)),
              static_cast<int64_t>(2));

    return g_failures == 0 ? 0 : 1;
}
