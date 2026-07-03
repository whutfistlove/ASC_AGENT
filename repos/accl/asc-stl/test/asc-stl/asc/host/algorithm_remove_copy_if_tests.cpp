#include "asc/std/algorithm.remove_copy_if.h"
#include <iostream>

static int g_failures = 0;

template <typename T>
static void expect_eq(const char* expr, T got, T expected)
{
    bool ok = (got == expected);
    std::cout << "[host][remove_copy_if] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

struct EqualToTwo
{
    bool operator()(int v) const { return v == 2; }
};

int main()
{
    // Basic test: remove elements equal to 2
    {
        int ia[] = {0, 1, 2, 3, 4, 2, 3, 4, 2};
        int ib[9] = {0};
        int expected[] = {0, 1, 3, 4, 3, 4};
        int* r = asc::std::remove_copy_if(ia, ia + 9, ib, EqualToTwo{});
        expect_eq("return offset (basic)", int(r - ib), 6);
        for (int i = 0; i < 6; ++i)
        {
            expect_eq("ib[i] (basic)", ib[i], expected[i]);
        }
        for (int i = 6; i < 9; ++i)
        {
            expect_eq("ib[i] untouched (basic)", ib[i], 0);
        }
    }

    // Empty range
    {
        int ia[] = {1, 2, 3};
        int ib[3] = {0};
        int* r = asc::std::remove_copy_if(ia, ia, ib, EqualToTwo{});
        expect_eq("return offset (empty range)", int(r - ib), 0);
        expect_eq("ib[0] untouched (empty)", ib[0], 0);
    }

    // All elements removed
    {
        int ia[] = {2, 2, 2};
        int ib[3] = {-1, -1, -1};
        int* r = asc::std::remove_copy_if(ia, ia + 3, ib, EqualToTwo{});
        expect_eq("return offset (all removed)", int(r - ib), 0);
        expect_eq("ib[0] untouched (all removed)", ib[0], -1);
    }

    // No elements removed
    {
        int ia[] = {1, 3, 5};
        int ib[3] = {0};
        int* r = asc::std::remove_copy_if(ia, ia + 3, ib, EqualToTwo{});
        expect_eq("return offset (none removed)", int(r - ib), 3);
        expect_eq("ib[0] (none removed)", ib[0], 1);
        expect_eq("ib[1] (none removed)", ib[1], 3);
        expect_eq("ib[2] (none removed)", ib[2], 5);
    }

    // Lambda predicate: remove negative numbers
    {
        int ia[] = {-3, 1, -2, 4, 0, -1};
        int ib[6] = {0};
        int expected[] = {1, 4, 0};
        auto is_negative = [](int v) { return v < 0; };
        int* r = asc::std::remove_copy_if(ia, ia + 6, ib, is_negative);
        expect_eq("return offset (lambda pred)", int(r - ib), 3);
        for (int i = 0; i < 3; ++i)
        {
            expect_eq("ib[i] (lambda pred)", ib[i], expected[i]);
        }
    }

    // Single element - not removed
    {
        int ia[] = {5};
        int ib[1] = {0};
        int* r = asc::std::remove_copy_if(ia, ia + 1, ib, EqualToTwo{});
        expect_eq("return offset (single not removed)", int(r - ib), 1);
        expect_eq("ib[0] (single not removed)", ib[0], 5);
    }

    // Single element - removed
    {
        int ia[] = {2};
        int ib[1] = {-1};
        int* r = asc::std::remove_copy_if(ia, ia + 1, ib, EqualToTwo{});
        expect_eq("return offset (single removed)", int(r - ib), 0);
        expect_eq("ib[0] untouched (single removed)", ib[0], -1);
    }

    return g_failures == 0 ? 0 : 1;
}
