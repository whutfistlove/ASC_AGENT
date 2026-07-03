#include "asc/std/__ranges/enable_borrowed_range.h"
#include <iostream>

static int g_failures = 0;

static void expect_true(const char* expr, bool cond)
{
    std::cout << "[host][enable_borrowed_range] " << expr << " = "
              << (cond ? "true" : "false") << " (expected true) "
              << (cond ? "OK" : "FAIL") << std::endl;
    if (!cond) ++g_failures;
}

static void expect_false(const char* expr, bool cond)
{
    std::cout << "[host][enable_borrowed_range] " << expr << " = "
              << (cond ? "true" : "false") << " (expected false) "
              << (!cond ? "OK" : "FAIL") << std::endl;
    if (cond) ++g_failures;
}

// Custom type for specialization test
struct MyRange {};

// Specialize enable_borrowed_range for MyRange
namespace asc { namespace std {
template <>
inline constexpr bool enable_borrowed_range<MyRange> = true;
}}

struct NotBorrowed {};

int main()
{
    // Default is false for fundamental types
    expect_false("enable_borrowed_range<int>", asc::std::enable_borrowed_range<int>);
    expect_false("enable_borrowed_range<double>", asc::std::enable_borrowed_range<double>);
    expect_false("enable_borrowed_range<char>", asc::std::enable_borrowed_range<char>);

    // Default is false for user types without specialization
    expect_false("enable_borrowed_range<NotBorrowed>", asc::std::enable_borrowed_range<NotBorrowed>);

    // Specialized to true
    expect_true("enable_borrowed_range<MyRange>", asc::std::enable_borrowed_range<MyRange>);

    // constexpr check
    static_assert(!asc::std::enable_borrowed_range<int>, "int should not be a borrowed range");
    static_assert(asc::std::enable_borrowed_range<MyRange>, "MyRange should be a borrowed range");

    return g_failures == 0 ? 0 : 1;
}
