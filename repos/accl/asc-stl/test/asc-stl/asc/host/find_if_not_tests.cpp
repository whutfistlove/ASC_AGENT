#include "asc/std/__algorithm/find_if_not.h"
#include <iostream>

static int g_failures = 0;

template <typename T>
static void expect_eq(const char* expr, T got, T expected)
{
    bool ok = (got == expected);
    std::cout << "[host][find_if_not] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

// Predicate functor: returns true if value != target (mirrors CCCL's Comparable)
struct NotEqual
{
    int target;
    NotEqual(int t) : target(t) {}
    bool operator()(int other) const { return target != other; }
};

int main()
{
    int arr[] = {2, 4, 6, 8};

    { // first element matches: NotEqual(2) is false for 2, true for 4,6,8
      auto it = asc::std::find_if_not(arr, arr + 4, NotEqual(2));
      expect_eq("find_if_not(arr, arr+4, NotEqual(2)) - *it", *it, 2);
      expect_eq("find_if_not(arr, arr+4, NotEqual(2)) - index", int(it - arr), 0);
    }

    { // empty range; return last
      auto it = asc::std::find_if_not(arr, arr, NotEqual(2));
      expect_eq("find_if_not(arr, arr, NotEqual(2)) - index", int(it - arr), 0);
    }

    { // multiple elements match; return first
      int arr2[] = {2, 4, 4, 8};
      auto it = asc::std::find_if_not(arr2, arr2 + 4, NotEqual(4));
      expect_eq("find_if_not(arr2, arr2+4, NotEqual(4)) - *it", *it, 4);
      expect_eq("find_if_not(arr2, arr2+4, NotEqual(4)) - index", int(it - arr2), 1);
    }

    { // some element matches (middle)
      auto it = asc::std::find_if_not(arr, arr + 4, NotEqual(6));
      expect_eq("find_if_not(arr, arr+4, NotEqual(6)) - *it", *it, 6);
      expect_eq("find_if_not(arr, arr+4, NotEqual(6)) - index", int(it - arr), 2);
    }

    { // last element matches
      auto it = asc::std::find_if_not(arr, arr + 4, NotEqual(8));
      expect_eq("find_if_not(arr, arr+4, NotEqual(8)) - *it", *it, 8);
      expect_eq("find_if_not(arr, arr+4, NotEqual(8)) - index", int(it - arr), 3);
    }

    { // no element matches; return last
      auto it = asc::std::find_if_not(arr, arr + 4, NotEqual(10));
      expect_eq("find_if_not(arr, arr+4, NotEqual(10)) - index", int(it - arr), 4);
    }

    return g_failures == 0 ? 0 : 1;
}
