#include "asc/std/__host_stdlib/ostream"
#include <iostream>
#include <sstream>

static int g_failures = 0;

static void expect_true(const char* expr, bool cond)
{
    std::cout << "[host][ostream] " << expr << " = " << (cond ? "true" : "false")
              << " (expected true) " << (cond ? "OK" : "FAIL") << std::endl;
    if (!cond) ++g_failures;
}

int main()
{
    // Verify that including asc/std/__host_stdlib/ostream makes std::ostream available
    {
        std::ostream& os = std::cout;
        (void)os;
        expect_true("std::ostream reference binding to std::cout works", true);
    }

    // Verify std::cout is usable for output
    std::cout << "[host][ostream] writing to std::cout works" << std::endl;
    expect_true("std::cout is usable", true);

    // Verify std::endl and std::flush (ostream manipulators) are available
    std::cout << "ostream manipulators test" << std::endl << std::flush;
    expect_true("std::endl and std::flush are available", true);

    // Verify operator<< on ostream works with various types
    {
        std::ostringstream oss;
        oss << 42 << " " << 3.14 << " " << 'x';
        expect_true("operator<< on ostringstream produces expected output",
                    oss.str() == "42 3.14 x");
    }

    // Verify std::ostringstream (derives from std::ostream) works
    {
        std::ostringstream oss;
        oss << "hello";
        expect_true("ostringstream basic output", oss.str() == "hello");
    }

    // Verify ASC_DEVICE_CODE is NOT defined on host
    {
#if defined(ASC_DEVICE_CODE)
        expect_true("ASC_DEVICE_CODE should NOT be defined on host", false);
#else
        expect_true("ASC_DEVICE_CODE is not defined on host", true);
#endif
    }

    return g_failures == 0 ? 0 : 1;
}
