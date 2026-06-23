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
    // Integer case: quad_fanout(1, 2, 3, 4)
    {
        int out0 = 0, out1 = 0, out2 = 0, out3 = 0, out4 = 0;
        asc::std::quad_fanout(1, 2, 3, 4, out0, out1, out2, out3, out4);
        expect_eq("quad_fanout(1,2,3,4) out0", out0, 3);
        expect_eq("quad_fanout(1,2,3,4) out1", out1, 5);
        expect_eq("quad_fanout(1,2,3,4) out2", out2, 7);
        expect_eq("quad_fanout(1,2,3,4) out3", out3, -3);
        expect_eq("quad_fanout(1,2,3,4) out4", out4, 10);
    }

    // Float case: quad_fanout(1.5f, -2.0f, 4.0f, 8.0f)
    {
        float out0 = 0.0f, out1 = 0.0f, out2 = 0.0f, out3 = 0.0f, out4 = 0.0f;
        asc::std::quad_fanout(1.5f, -2.0f, 4.0f, 8.0f, out0, out1, out2, out3, out4);
        expect_eq("quad_fanout(1.5f,-2.0f,4.0f,8.0f) out0", out0, -0.5f);
        expect_eq("quad_fanout(1.5f,-2.0f,4.0f,8.0f) out1", out1, 2.0f);
        expect_eq("quad_fanout(1.5f,-2.0f,4.0f,8.0f) out2", out2, 12.0f);
        expect_eq("quad_fanout(1.5f,-2.0f,4.0f,8.0f) out3", out3, -6.5f);
        expect_eq("quad_fanout(1.5f,-2.0f,4.0f,8.0f) out4", out4, 11.5f);
    }

    // Zero inputs
    {
        int out0 = 0, out1 = 0, out2 = 0, out3 = 0, out4 = 0;
        asc::std::quad_fanout(0, 0, 0, 0, out0, out1, out2, out3, out4);
        expect_eq("quad_fanout(0,0,0,0) out0", out0, 0);
        expect_eq("quad_fanout(0,0,0,0) out1", out1, 0);
        expect_eq("quad_fanout(0,0,0,0) out2", out2, 0);
        expect_eq("quad_fanout(0,0,0,0) out3", out3, 0);
        expect_eq("quad_fanout(0,0,0,0) out4", out4, 0);
    }

    // Negative integers
    {
        int out0 = 0, out1 = 0, out2 = 0, out3 = 0, out4 = 0;
        asc::std::quad_fanout(-5, -3, -1, -7, out0, out1, out2, out3, out4);
        expect_eq("quad_fanout(-5,-3,-1,-7) out0", out0, -8);
        expect_eq("quad_fanout(-5,-3,-1,-7) out1", out1, -4);
        expect_eq("quad_fanout(-5,-3,-1,-7) out2", out2, -8);
        expect_eq("quad_fanout(-5,-3,-1,-7) out3", out3, 2);
        expect_eq("quad_fanout(-5,-3,-1,-7) out4", out4, -16);
    }

    return g_failures == 0 ? 0 : 1;
}
