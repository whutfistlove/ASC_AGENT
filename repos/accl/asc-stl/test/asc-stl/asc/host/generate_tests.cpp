#include "asc/std/__algorithm/generate.h"
#include <iostream>

static int g_failures = 0;

template <typename T>
static void expect_eq(const char* expr, T got, T expected)
{
    bool ok = (got == expected);
    std::cout << "[host][generate] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

struct gen_test
{
    int operator()() const { return 1; }
};

struct gen_counter
{
    int val_;
    gen_counter() : val_(0) {}
    int operator()() { return val_++; }
};

int main()
{
    // Test 1: constant generator fills range (mirrors CCCL upstream test)
    {
        const int N = 5;
        int ia[N + 1] = {0};
        asc::std::generate(ia, ia + N, gen_test());
        for (int i = 0; i < N; ++i)
        {
            expect_eq("ia[i] after generate with gen_test", ia[i], 1);
        }
        expect_eq("ia[N] beyond range untouched", ia[N], 0);
    }

    // Test 2: stateful counter generator
    {
        const int N = 5;
        int ia[N] = {0};
        asc::std::generate(ia, ia + N, gen_counter());
        for (int i = 0; i < N; ++i)
        {
            expect_eq("ia[i] after generate with counter", ia[i], i);
        }
    }

    // Test 3: empty range — nothing should be written
    {
        int ia[1] = {42};
        asc::std::generate(ia, ia, gen_test());
        expect_eq("ia[0] after generate on empty range", ia[0], 42);
    }

    // Test 4: single element range
    {
        int ia[1] = {0};
        asc::std::generate(ia, ia + 1, gen_test());
        expect_eq("ia[0] after generate on single element", ia[0], 1);
    }

    // Test 5: lambda generator with float
    {
        const int N = 4;
        float fa[N] = {0.0f, 0.0f, 0.0f, 0.0f};
        float val = 3.14f;
        asc::std::generate(fa, fa + N, [&val]() { return val; });
        for (int i = 0; i < N; ++i)
        {
            expect_eq("fa[i] after generate with lambda", fa[i], 3.14f);
        }
    }

    // Test 6: generate overwrites existing values
    {
        const int N = 3;
        int ia[N] = {99, 88, 77};
        asc::std::generate(ia, ia + N, gen_test());
        for (int i = 0; i < N; ++i)
        {
            expect_eq("ia[i] overwritten by generate", ia[i], 1);
        }
    }

    return g_failures == 0 ? 0 : 1;
}
