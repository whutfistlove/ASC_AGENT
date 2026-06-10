#include "asc/std/__utility/swap.h"
#include <iostream>

static int g_failures = 0;

template <typename T>
static void expect_eq(const char* expr, T got, T expected)
{
    bool ok = (got == expected);
    std::cout << "[host][swap] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

int main()
{
    int a = 1;
    int b = 2;
    asc::std::swap(a, b);
    expect_eq("swap(a=1,b=2) -> a", a, 2);
    expect_eq("swap(a=1,b=2) -> b", b, 1);

    float x = 3.5f;
    float y = -1.0f;
    asc::std::swap(x, y);
    expect_eq("swap(x=3.5,y=-1) -> x", x, -1.0f);
    expect_eq("swap(x=3.5,y=-1) -> y", y, 3.5f);

    int u[3] = {1, 2, 3};
    int v[3] = {4, 5, 6};
    asc::std::swap(u, v);
    expect_eq("swap(u,v) -> u[0]", u[0], 4);
    expect_eq("swap(u,v) -> u[1]", u[1], 5);
    expect_eq("swap(u,v) -> u[2]", u[2], 6);
    expect_eq("swap(u,v) -> v[0]", v[0], 1);
    expect_eq("swap(u,v) -> v[1]", v[1], 2);
    expect_eq("swap(u,v) -> v[2]", v[2], 3);

    return g_failures == 0 ? 0 : 1;
}
