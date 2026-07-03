#include "asc/std/__host_stdlib/istream"
#include <iostream>
#include <sstream>
#include <string>

int g_failures = 0;

template <typename T>
void expect_eq(const char* expr, const T& got, const T& expected) {
    if (got != expected) {
        std::cout << "[host][istream] " << expr << " = " << got << " (expected " << expected << ") FAIL" << std::endl;
        g_failures++;
    } else {
        std::cout << "[host][istream] " << expr << " = " << got << " (expected " << expected << ") OK" << std::endl;
    }
}

int main() {
    // Verify that std::istream is available and functional via std::istringstream
    std::istringstream iss("hello 42");
    std::string s;
    int i = 0;
    iss >> s >> i;
    
    expect_eq("s == \"hello\"", s, std::string("hello"));
    expect_eq("i == 42", i, 42);
    
    return g_failures == 0 ? 0 : 1;
}
