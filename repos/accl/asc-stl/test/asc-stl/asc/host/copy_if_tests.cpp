#include "asc/std/__algorithm/copy_if.h"
#include <iostream>

static int g_failures = 0;

template <typename T>
static void expect_eq(const char* expr, T got, T expected)
{
    bool ok = (got == expected);
    std::cout << "[host][copy_if] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

int main()
{
    // Test 1: Copy multiples of 3 from range [0, 1000)
    {
        const int N = 1000;
        int ia[N];
        for (int i = 0; i < N; ++i) ia[i] = i;
        int ib[N] = {0};

        auto pred = [](int v) { return v % 3 == 0; };
        int* r = asc::std::copy_if(ia, ia + N, ib, pred);

        int expected_count = N / 3 + 1; // 0, 3, 6, ..., 999 => 334 elements
        expect_eq("copy_if mod3: return offset", static_cast<int>(r - ib), expected_count);

        bool all_mod3 = true;
        for (int i = 0; i < expected_count; ++i) {
            if (ib[i] % 3 != 0) all_mod3 = false;
        }
        expect_eq("copy_if mod3: all outputs divisible by 3", all_mod3 ? 1 : 0, 1);
    }

    // Test 2: Copy elements equal to 6
    {
        const int N = 5;
        int ia[N] = {2, 4, 6, 8, 6};
        int ic[N + 2] = {0};

        auto pred = [](int v) { return v == 6; };
        int* r = asc::std::copy_if(ia, ia + N, ic, pred);

        expect_eq("copy_if eq6: return offset", static_cast<int>(r - ic), 2);
        expect_eq("copy_if eq6: ic[0]", ic[0], 6);
        expect_eq("copy_if eq6: ic[1]", ic[1], 6);
        expect_eq("copy_if eq6: ic[2] untouched", ic[2], 0);
    }

    // Test 3: Empty range (first == last)
    {
        int ia[1] = {42};
        int ib[1] = {0};
        auto pred = [](int v) { return v % 3 == 0; };
        int* r = asc::std::copy_if(ia, ia, ib, pred);
        expect_eq("copy_if empty range: return offset", static_cast<int>(r - ib), 0);
    }

    // Test 4: No matching elements
    {
        int ia[3] = {1, 2, 4};
        int ib[3] = {0, 0, 0};
        auto pred = [](int v) { return v % 3 == 0; };
        int* r = asc::std::copy_if(ia, ia + 3, ib, pred);
        expect_eq("copy_if no match: return offset", static_cast<int>(r - ib), 0);
        expect_eq("copy_if no match: ib[0] untouched", ib[0], 0);
    }

    // Test 5: All elements match
    {
        int ia[4] = {3, 6, 9, 12};
        int ib[4] = {0};
        auto pred = [](int v) { return v % 3 == 0; };
        int* r = asc::std::copy_if(ia, ia + 4, ib, pred);
        expect_eq("copy_if all match: return offset", static_cast<int>(r - ib), 4);
        expect_eq("copy_if all match: ib[0]", ib[0], 3);
        expect_eq("copy_if all match: ib[3]", ib[3], 12);
    }

    return g_failures == 0 ? 0 : 1;
}
