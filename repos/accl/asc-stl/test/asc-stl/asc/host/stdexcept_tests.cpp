#include "asc/std/__host_stdlib/stdexcept"
#include <iostream>
#include <string>

static int g_failures = 0;

static void expect_eq(const char* expr, const std::string& got, const std::string& expected)
{
    bool ok = (got == expected);
    std::cout << "[host][stdexcept] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

int main()
{
    std::cout << "[host][stdexcept] Header asc/std/__host_stdlib/stdexcept included OK" << std::endl;

    {
        std::logic_error le("logic_error_msg");
        expect_eq("std::logic_error(\"logic_error_msg\").what()", le.what(), std::string("logic_error_msg"));
    }

    {
        std::runtime_error re("runtime_error_msg");
        expect_eq("std::runtime_error(\"runtime_error_msg\").what()", re.what(), std::string("runtime_error_msg"));
    }

    {
        std::domain_error de("domain_error_msg");
        expect_eq("std::domain_error(\"domain_error_msg\").what()", de.what(), std::string("domain_error_msg"));
    }

    {
        std::invalid_argument ia("invalid_argument_msg");
        expect_eq("std::invalid_argument(\"invalid_argument_msg\").what()", ia.what(), std::string("invalid_argument_msg"));
    }

    {
        std::length_error le("length_error_msg");
        expect_eq("std::length_error(\"length_error_msg\").what()", le.what(), std::string("length_error_msg"));
    }

    {
        std::out_of_range oor("out_of_range_msg");
        expect_eq("std::out_of_range(\"out_of_range_msg\").what()", oor.what(), std::string("out_of_range_msg"));
    }

    {
        std::range_error re("range_error_msg");
        expect_eq("std::range_error(\"range_error_msg\").what()", re.what(), std::string("range_error_msg"));
    }

    {
        std::overflow_error oe("overflow_error_msg");
        expect_eq("std::overflow_error(\"overflow_error_msg\").what()", oe.what(), std::string("overflow_error_msg"));
    }

    {
        std::underflow_error ue("underflow_error_msg");
        expect_eq("std::underflow_error(\"underflow_error_msg\").what()", ue.what(), std::string("underflow_error_msg"));
    }

    return g_failures == 0 ? 0 : 1;
}
