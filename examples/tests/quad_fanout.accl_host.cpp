#include "asc/std/__algorithm/quad_fanout.h"
#include <iostream>

static int g_failures = 0;

template <typename T>
static void expect_eq(const char* expr, T got, T expected)
{
    bool ok = (got == expected);
    std::cout << "[host][quad_fanout] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

int main()
{
    {
        int a = 1, b = 2, c = 3, d = 4;
        int out0 = 0, out1 = 0, out2 = 0, out3 = 0, out4 = 0;
        asc::std::quad_fanout(a, b, c, d, out0, out1, out2, out3, out4);
        expect_eq("quad_fanout(1,2,3,4) -> out0", out0, 3);
        expect_eq("quad_fanout(1,2,3,4) -> out1", out1, 5);
        expect_eq("quad_fanout(1,2,3,4) -> out2", out2, 7);
        expect_eq("quad_fanout(1,2,3,4) -> out3", out3, -3);
        expect_eq("quad_fanout(1,2,3,4) -> out4", out4, 10);
    }

    {
        float a = 1.5f, b = -2.0f, c = 4.0f, d = 8.0f;
        float out0 = 0.0f, out1 = 0.0f, out2 = 0.0f, out3 = 0.0f, out4 = 0.0f;
        asc::std::quad_fanout(a, b, c, d, out0, out1, out2, out3, out4);
        expect_eq("quad_fanout(1.5,-2,4,8) -> out0", out0, -0.5f);
        expect_eq("quad_fanout(1.5,-2,4,8) -> out1", out1, 2.0f);
        expect_eq("quad_fanout(1.5,-2,4,8) -> out2", out2, 12.0f);
        expect_eq("quad_fanout(1.5,-2,4,8) -> out3", out3, -6.5f);
        expect_eq("quad_fanout(1.5,-2,4,8) -> out4", out4, 11.5f);
    }

    return g_failures == 0 ? 0 : 1;
}
