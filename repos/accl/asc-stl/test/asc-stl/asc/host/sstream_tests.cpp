#include "asc/std/__host_stdlib/sstream"
#include <iostream>
#include <string>

static int g_failures = 0;

static void expect_eq(const char* expr, const std::string& got, const std::string& expected)
{
    bool ok = (got == expected);
    std::cout << "[host][sstream] " << expr << " = \"" << got
              << "\" (expected \"" << expected << "\") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

static void expect_eq(const char* expr, int got, int expected)
{
    bool ok = (got == expected);
    std::cout << "[host][sstream] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

int main()
{
    // Test basic stringstream: write and read back
    {
        std::stringstream ss;
        ss << "hello " << 42;
        expect_eq("ss.str()", ss.str(), std::string("hello 42"));
    }

    // Test istringstream: parse integers from string
    {
        std::istringstream iss("100 200");
        int a = 0, b = 0;
        iss >> a >> b;
        expect_eq("istringstream a", a, 100);
        expect_eq("istringstream b", b, 200);
    }

    // Test ostringstream: format to string
    {
        std::ostringstream oss;
        oss << 3.14;
        expect_eq("ostringstream str", oss.str(), std::string("3.14"));
    }

    // Test str() setter and getter
    {
        std::stringstream ss;
        ss.str("abc");
        expect_eq("str() getter", ss.str(), std::string("abc"));
    }

    // Test clear and reuse
    {
        std::stringstream ss;
        ss << "first";
        ss.str("");
        ss << "second";
        expect_eq("clear and reuse", ss.str(), std::string("second"));
    }

    // Test integer round-trip via stringstream
    {
        std::stringstream ss;
        int val = 9999;
        ss << val;
        int back = 0;
        ss >> back;
        expect_eq("int round-trip", back, 9999);
    }

    // Test istringstream with mixed types
    {
        std::istringstream iss("42 hello");
        int n = 0;
        std::string s;
        iss >> n >> s;
        expect_eq("mixed int", n, 42);
        expect_eq("mixed string", s, std::string("hello"));
    }

    return g_failures == 0 ? 0 : 1;
}
