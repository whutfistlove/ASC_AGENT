#include "asc/std/__algorithm/for_each.h"
#include <iostream>

static int g_failures = 0;

template <typename T>
static void expect_eq(const char* expr, T got, T expected)
{
    bool ok = (got == expected);
    std::cout << "[host][for_each] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

struct add_two
{
    void operator()(int& a) const
    {
        a += 2;
    }
};

struct for_each_test
{
    int count;
    for_each_test(int c) : count(c) {}
    void operator()(int& i)
    {
        ++i;
        ++count;
    }
};

int main()
{
    // Test 1: add_two functor (from CCCL test_constexpr)
    {
        int ia[] = {1, 3, 6, 7};
        int expected[] = {3, 5, 8, 9};
        asc::std::for_each(ia, ia + 4, add_two{});
        for (int i = 0; i < 4; ++i)
        {
            expect_eq("ia[i] after add_two", ia[i], expected[i]);
        }
    }

    // Test 2: for_each_test functor with state tracking (from CCCL main)
    {
        int ia[] = {0, 1, 2, 3, 4, 5};
        for_each_test f = asc::std::for_each(ia, ia + 6, for_each_test(0));
        expect_eq("f.count", f.count, 6);
        for (int i = 0; i < 6; ++i)
        {
            expect_eq("ia[i] after for_each_test", ia[i], i + 1);
        }
    }

    // Test 3: empty range — functor must not be invoked
    {
        int ia[] = {5};
        for_each_test f = asc::std::for_each(ia, ia, for_each_test(0));
        expect_eq("f.count (empty range)", f.count, 0);
        expect_eq("ia[0] (empty range)", ia[0], 5);
    }

    // Test 4: single element range
    {
        int ia[] = {10};
        asc::std::for_each(ia, ia + 1, add_two{});
        expect_eq("ia[0] after add_two (single)", ia[0], 12);
    }

    // Test 5: returned functor carries updated state
    {
        int ia[] = {10, 20, 30};
        for_each_test f = asc::std::for_each(ia, ia + 3, for_each_test(7));
        expect_eq("f.count (initial 7 + 3 calls)", f.count, 10);
    }

    return g_failures == 0 ? 0 : 1;
}
