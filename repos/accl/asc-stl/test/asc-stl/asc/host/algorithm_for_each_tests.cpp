#include "asc/std/algorithm.for_each.h"
#include <iostream>
#include <vector>

static int g_failures = 0;

template <typename T>
static void expect_eq(const char* expr, T got, T expected)
{
    bool ok = (got == expected);
    std::cout << "[host][for_each] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

int main()
{
    // Basic test: sum elements via for_each
    {
        int arr[] = {1, 2, 3, 4, 5};
        int sum = 0;
        auto summer = [&sum](int x) { sum += x; };
        auto result = asc::std::for_each(arr, arr + 5, summer);
        expect_eq("sum of {1,2,3,4,5}", sum, 15);
        (void)result;
    }

    // Test: returned function is the same functor (can be reused)
    {
        int arr[] = {10, 20, 30};
        int count = 0;
        auto counter = [&count](int) { ++count; };
        auto returned = asc::std::for_each(arr, arr + 3, counter);
        expect_eq("count after first for_each", count, 3);
        // Apply returned functor manually
        returned(99);
        expect_eq("count after manual call", count, 4);
    }

    // Test: empty range
    {
        int arr[] = {1, 2, 3};
        int sum = 0;
        auto summer = [&sum](int x) { sum += x; };
        asc::std::for_each(arr, arr + 0, summer);
        expect_eq("sum over empty range", sum, 0);
    }

    // Test: float array
    {
        float arr[] = {1.5f, 2.5f, 3.0f};
        float sum = 0.0f;
        asc::std::for_each(arr, arr + 3, [&sum](float x) { sum += x; });
        expect_eq("float sum of {1.5,2.5,3.0}", sum, 7.0f);
    }

    // Test: modify elements in place
    {
        int arr[] = {1, 2, 3};
        asc::std::for_each(arr, arr + 3, [](int& x) { x *= 2; });
        expect_eq("arr[0] after double", arr[0], 2);
        expect_eq("arr[1] after double", arr[1], 4);
        expect_eq("arr[2] after double", arr[2], 6);
    }

    // Test: with vector iterators
    {
        std::vector<int> v = {5, 10, 15};
        int product = 1;
        asc::std::for_each(v.begin(), v.end(), [&product](int x) { product *= x; });
        expect_eq("product of {5,10,15}", product, 750);
    }

    return g_failures == 0 ? 0 : 1;
}
