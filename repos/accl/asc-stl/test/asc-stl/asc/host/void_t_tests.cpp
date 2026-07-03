#include "asc/std/__type_traits/void_t.h"
#include <iostream>
#include <type_traits>

static int g_failures = 0;

static void expect_true(const char* expr, bool cond)
{
    std::cout << "[host][void_t] " << expr << " = " << (cond ? "true" : "false")
              << " (expected true) " << (cond ? "OK" : "FAIL") << std::endl;
    if (!cond) ++g_failures;
}

// Test that void_t<T> is void for various T
template <class T>
static void test1()
{
    expect_true("void_t<T> is void", std::is_same_v<void, asc::std::void_t<T>>);
    expect_true("void_t<const T> is void", std::is_same_v<void, asc::std::void_t<const T>>);
    expect_true("void_t<volatile T> is void", std::is_same_v<void, asc::std::void_t<volatile T>>);
    expect_true("void_t<const volatile T> is void", std::is_same_v<void, asc::std::void_t<const volatile T>>);
}

// Test that void_t<T, U> is void for various T, U
template <class T, class U>
static void test2()
{
    expect_true("void_t<T, U> is void", std::is_same_v<void, asc::std::void_t<T, U>>);
    expect_true("void_t<const T, U> is void", std::is_same_v<void, asc::std::void_t<const T, U>>);
    expect_true("void_t<volatile T, U> is void", std::is_same_v<void, asc::std::void_t<volatile T, U>>);
    expect_true("void_t<const volatile T, U> is void", std::is_same_v<void, asc::std::void_t<const volatile T, U>>);

    expect_true("void_t<U, T> is void", std::is_same_v<void, asc::std::void_t<U, T>>);
    expect_true("void_t<U, const T> is void", std::is_same_v<void, asc::std::void_t<U, const T>>);
    expect_true("void_t<U, volatile T> is void", std::is_same_v<void, asc::std::void_t<U, volatile T>>);
    expect_true("void_t<U, const volatile T> is void", std::is_same_v<void, asc::std::void_t<U, const volatile T>>);

    expect_true("void_t<T, const U> is void", std::is_same_v<void, asc::std::void_t<T, const U>>);
    expect_true("void_t<const T, const U> is void", std::is_same_v<void, asc::std::void_t<const T, const U>>);
    expect_true("void_t<volatile T, const U> is void", std::is_same_v<void, asc::std::void_t<volatile T, const U>>);
    expect_true("void_t<const volatile T, const U> is void", std::is_same_v<void, asc::std::void_t<const volatile T, const U>>);
}

class Class
{
public:
    ~Class() {}
};

int main()
{
    // void_t<> (no arguments) is void
    expect_true("void_t<> is void", std::is_same_v<void, asc::std::void_t<>>);

    test1<void>();
    test1<int>();
    test1<double>();
    test1<int&>();
    test1<Class>();
    test1<Class[]>();
    test1<Class[5]>();

    test2<void, int>();
    test2<double, int>();
    test2<int&, int>();
    test2<Class&, bool>();
    test2<void*, int&>();

    // Multi-arg void_t
    expect_true("void_t<int, double const&, Class, volatile int[], void> is void",
                std::is_same_v<void, asc::std::void_t<int, double const&, Class, volatile int[], void>>);

    return g_failures == 0 ? 0 : 1;
}
