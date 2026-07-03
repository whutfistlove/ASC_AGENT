#include "asc/std/algorithm.none_of.h"
#include <iostream>
#include <vector>

static int g_failures = 0;

static void expect_true(const char* expr, bool got)
{
    std::cout << "[host][none_of] " << expr << " = " << (got ? "true" : "false")
              << " (expected true) " << (got ? "OK" : "FAIL") << std::endl;
    if (!got) ++g_failures;
}

static void expect_false(const char* expr, bool got)
{
    std::cout << "[host][none_of] " << expr << " = " << (got ? "true" : "false")
              << " (expected false) " << (got ? "FAIL" : "OK") << std::endl;
    if (got) ++g_failures;
}

int main()
{
    // Empty range: none_of should return true
    {
        std::vector<int> v;
        expect_true("none_of(empty, pred)", asc::std::none_of(v.begin(), v.end(), [](int x) { return x > 0; }));
    }

    // No element satisfies predicate
    {
        int arr[] = {-1, -2, -3, -4, -5};
        expect_true("none_of(all_negative, x>0)", asc::std::none_of(arr, arr + 5, [](int x) { return x > 0; }));
    }

    // Some elements satisfy predicate
    {
        int arr[] = {-1, 2, -3, 4, -5};
        expect_false("none_of(mixed, x>0)", asc::std::none_of(arr, arr + 5, [](int x) { return x > 0; }));
    }

    // All elements satisfy predicate
    {
        int arr[] = {1, 2, 3, 4, 5};
        expect_false("none_of(all_positive, x>0)", asc::std::none_of(arr, arr + 5, [](int x) { return x > 0; }));
    }

    // Single element: satisfies predicate
    {
        int arr[] = {5};
        expect_false("none_of({5}, x>0)", asc::std::none_of(arr, arr + 1, [](int x) { return x > 0; }));
    }

    // Single element: does not satisfy predicate
    {
        int arr[] = {-5};
        expect_true("none_of({-5}, x>0)", asc::std::none_of(arr, arr + 1, [](int x) { return x > 0; }));
    }

    // Float range
    {
        float arr[] = {0.1f, 0.2f, 0.3f};
        expect_false("none_of(floats, x>0)", asc::std::none_of(arr, arr + 3, [](float x) { return x > 0.0f; }));
    }

    // Float range: none satisfy
    {
        float arr[] = {-0.1f, -0.2f, -0.3f};
        expect_true("none_of(neg_floats, x>0)", asc::std::none_of(arr, arr + 3, [](float x) { return x > 0.0f; }));
    }

    // Predicate: is_zero
    {
        int arr[] = {1, 2, 3, 4, 5};
        expect_true("none_of(1..5, x==0)", asc::std::none_of(arr, arr + 5, [](int x) { return x == 0; }));
    }

    // Predicate: is_zero with a zero present
    {
        int arr[] = {1, 0, 3, 4, 5};
        expect_false("none_of(1,0,3,4,5, x==0)", asc::std::none_of(arr, arr + 5, [](int x) { return x == 0; }));
    }

    // Range of one element at the end satisfies
    {
        int arr[] = {1, 2, 3, 4, 5};
        expect_false("none_of(1..5, x==5)", asc::std::none_of(arr, arr + 5, [](int x) { return x == 5; }));
    }

    return g_failures == 0 ? 0 : 1;
}
