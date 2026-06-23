#include "asc/std/__algorithm/reverse_copy.h"
#include <iostream>

static int g_failures = 0;

template <typename T>
static void expect_eq(const char* expr, T got, T expected)
{
    bool ok = (got == expected);
    std::cout << "[host][reverse_copy] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

static void expect_true(const char* expr, bool cond)
{
    std::cout << "[host][reverse_copy] " << expr << " = " << (cond ? "true" : "false")
              << " (expected true) " << (cond ? "OK" : "FAIL") << std::endl;
    if (!cond) ++g_failures;
}

int main()
{
    // Test 1: empty range — nothing copied, returned iterator == result
    {
        const int ia[] = {0};
        int ja[1] = {-1};
        int* r = asc::std::reverse_copy(ia, ia, ja);
        expect_true("empty: returned == ja", r == ja);
        expect_eq("empty: ja[0] unchanged", ja[0], -1);
    }

    // Test 2: single element
    {
        const int ia[] = {5};
        int ja[1] = {-1};
        int* r = asc::std::reverse_copy(ia, ia + 1, ja);
        expect_true("single: returned == ja+1", r == ja + 1);
        expect_eq("single: ja[0] == 5", ja[0], 5);
    }

    // Test 3: two elements
    {
        const int ib[] = {0, 1};
        int jb[2] = {-1, -1};
        int* r = asc::std::reverse_copy(ib, ib + 2, jb);
        expect_true("two: returned == jb+2", r == jb + 2);
        expect_eq("two: jb[0] == 1", jb[0], 1);
        expect_eq("two: jb[1] == 0", jb[1], 0);
    }

    // Test 4: three elements
    {
        const int ic[] = {0, 1, 2};
        int jc[3] = {-1, -1, -1};
        int* r = asc::std::reverse_copy(ic, ic + 3, jc);
        expect_true("three: returned == jc+3", r == jc + 3);
        expect_eq("three: jc[0] == 2", jc[0], 2);
        expect_eq("three: jc[1] == 1", jc[1], 1);
        expect_eq("three: jc[2] == 0", jc[2], 0);
    }

    // Test 5: four elements
    {
        const int id[] = {0, 1, 2, 3};
        int jd[4] = {-1, -1, -1, -1};
        int* r = asc::std::reverse_copy(id, id + 4, jd);
        expect_true("four: returned == jd+4", r == jd + 4);
        expect_eq("four: jd[0] == 3", jd[0], 3);
        expect_eq("four: jd[1] == 2", jd[1], 2);
        expect_eq("four: jd[2] == 1", jd[2], 1);
        expect_eq("four: jd[3] == 0", jd[3], 0);
    }

    // Test 6: float values
    {
        const float fa[] = {1.5f, 2.5f, 3.5f};
        float fb[3] = {-1.0f, -1.0f, -1.0f};
        float* r = asc::std::reverse_copy(fa, fa + 3, fb);
        expect_true("float: returned == fb+3", r == fb + 3);
        expect_eq("float: fb[0]", fb[0], 3.5f);
        expect_eq("float: fb[1]", fb[1], 2.5f);
        expect_eq("float: fb[2]", fb[2], 1.5f);
    }

    // Test 7: negative values
    {
        const int in[] = {-3, -2, -1, 0, 1};
        int out[5] = {0, 0, 0, 0, 0};
        int* r = asc::std::reverse_copy(in, in + 5, out);
        expect_true("neg: returned == out+5", r == out + 5);
        expect_eq("neg: out[0] == 1", out[0], 1);
        expect_eq("neg: out[1] == 0", out[1], 0);
        expect_eq("neg: out[2] == -1", out[2], -1);
        expect_eq("neg: out[3] == -2", out[3], -2);
        expect_eq("neg: out[4] == -3", out[4], -3);
    }

    return g_failures == 0 ? 0 : 1;
}
