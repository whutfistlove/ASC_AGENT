#include "asc/std/__algorithm/replace_copy_if.h"
#include <iostream>

static int g_failures = 0;

template <typename T>
static void expect_eq(const char* expr, T got, T expected)
{
    bool ok = (got == expected);
    std::cout << "[host][replace_copy_if] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

static void expect_true(const char* expr, bool cond)
{
    std::cout << "[host][replace_copy_if] " << expr << " = " << (cond ? "true" : "false")
              << " (expected true) " << (cond ? "OK" : "FAIL") << std::endl;
    if (!cond) ++g_failures;
}

// Predicate: true if value equals 2
struct EqualToTwo
{
    bool operator()(int v) const { return v == 2; }
};

// Predicate: true if value is negative
struct IsNegative
{
    bool operator()(int v) const { return v < 0; }
};

// Predicate: true if value is even
struct IsEven
{
    bool operator()(int v) const { return v % 2 == 0; }
};

// Predicate for float: true if value > threshold
struct GreaterThanThreshold
{
    float threshold;
    GreaterThanThreshold(float t) : threshold(t) {}
    bool operator()(float v) const { return v > threshold; }
};

void test_basic_int()
{
    const int N = 5;
    const int ia[N] = {0, 1, 2, 3, 4};
    int ib[N] = {0};
    const int expected[N] = {0, 1, 5, 3, 4};

    int* r = asc::std::replace_copy_if(ia, ia + N, ib, EqualToTwo{}, 5);

    expect_true("return value == ib + N", r == ib + N);
    for (int i = 0; i < N; ++i)
    {
        expect_eq("ib[i] (basic int)", ib[i], expected[i]);
    }
}

void test_negative_replacement()
{
    const int N = 6;
    const int ia[N] = {3, -1, 4, -5, 0, -2};
    int ib[N] = {0};
    const int expected[N] = {3, 99, 4, 99, 0, 99};

    int* r = asc::std::replace_copy_if(ia, ia + N, ib, IsNegative{}, 99);

    expect_true("return value == ib + N (negative)", r == ib + N);
    for (int i = 0; i < N; ++i)
    {
        expect_eq("ib[i] (negative replace)", ib[i], expected[i]);
    }
}

void test_even_replacement()
{
    const int N = 5;
    const int ia[N] = {1, 2, 3, 4, 5};
    int ib[N] = {0};
    const int expected[N] = {1, -1, 3, -1, 5};

    int* r = asc::std::replace_copy_if(ia, ia + N, ib, IsEven{}, -1);

    expect_true("return value == ib + N (even)", r == ib + N);
    for (int i = 0; i < N; ++i)
    {
        expect_eq("ib[i] (even replace)", ib[i], expected[i]);
    }
}

void test_empty_range()
{
    int ia[1] = {42};
    int ib[1] = {-1};

    int* r = asc::std::replace_copy_if(ia, ia, ib, EqualToTwo{}, 5);

    expect_true("return value == ib (empty range)", r == ib);
    expect_eq("ib[0] untouched (empty range)", ib[0], -1);
}

void test_single_element_match()
{
    int ia[1] = {2};
    int ib[1] = {0};
    const int expected = 7;

    int* r = asc::std::replace_copy_if(ia, ia + 1, ib, EqualToTwo{}, 7);

    expect_true("return value == ib + 1 (single match)", r == ib + 1);
    expect_eq("ib[0] (single match)", ib[0], expected);
}

void test_single_element_no_match()
{
    int ia[1] = {3};
    int ib[1] = {0};

    int* r = asc::std::replace_copy_if(ia, ia + 1, ib, EqualToTwo{}, 7);

    expect_true("return value == ib + 1 (single no match)", r == ib + 1);
    expect_eq("ib[0] (single no match)", ib[0], 3);
}

void test_all_match()
{
    const int N = 4;
    const int ia[N] = {2, 2, 2, 2};
    int ib[N] = {0};
    const int expected[N] = {9, 9, 9, 9};

    int* r = asc::std::replace_copy_if(ia, ia + N, ib, EqualToTwo{}, 9);

    expect_true("return value == ib + N (all match)", r == ib + N);
    for (int i = 0; i < N; ++i)
    {
        expect_eq("ib[i] (all match)", ib[i], expected[i]);
    }
}

void test_none_match()
{
    const int N = 4;
    const int ia[N] = {1, 3, 5, 7};
    int ib[N] = {0};

    int* r = asc::std::replace_copy_if(ia, ia + N, ib, EqualToTwo{}, 9);

    expect_true("return value == ib + N (none match)", r == ib + N);
    for (int i = 0; i < N; ++i)
    {
        expect_eq("ib[i] (none match)", ib[i], ia[i]);
    }
}

void test_float_with_threshold()
{
    const int N = 5;
    const float ia[N] = {1.0f, 5.0f, 3.0f, 8.0f, 2.0f};
    float ib[N] = {0.0f};
    const float expected[N] = {1.0f, -1.0f, 3.0f, -1.0f, 2.0f};
    // Replace values > 4.0f with -1.0f

    float* r = asc::std::replace_copy_if(ia, ia + N, ib, GreaterThanThreshold{4.0f}, -1.0f);

    expect_true("return value == ib + N (float)", r == ib + N);
    for (int i = 0; i < N; ++i)
    {
        bool ok = (ib[i] == expected[i]);
        std::cout << "[host][replace_copy_if] ib[" << i << "] (float threshold) = " << ib[i]
                  << " (expected " << expected[i] << ") " << (ok ? "OK" : "FAIL") << std::endl;
        if (!ok) ++g_failures;
    }
}

int main()
{
    test_basic_int();
    test_negative_replacement();
    test_even_replacement();
    test_empty_range();
    test_single_element_match();
    test_single_element_no_match();
    test_all_match();
    test_none_match();
    test_float_with_threshold();

    return g_failures == 0 ? 0 : 1;
}
