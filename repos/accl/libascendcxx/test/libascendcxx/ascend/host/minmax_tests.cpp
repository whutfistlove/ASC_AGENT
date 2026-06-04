#include <iostream>
#include "ascend/std/__algorithm/minmax.h"

template<typename T, typename U>
void expect_eq(const char* expr, T got, U expected) {
    bool pass = (got == expected);
    std::cout << "[host][minmax] " << (pass ? "PASS" : "FAIL") << ": " << expr << " == " << got << " (expected " << expected << ")" << std::endl;
}

int main() {
    auto res1 = ascend::std::minmax(1, 2);
    expect_eq("ascend::std::minmax(1, 2).first", res1.first, 1);
    expect_eq("ascend::std::minmax(1, 2).second", res1.second, 2);

    auto res2 = ascend::std::minmax(3, 2);
    expect_eq("ascend::std::minmax(3, 2).first", res2.first, 2);
    expect_eq("ascend::std::minmax(3, 2).second", res2.second, 3);

    auto res3 = ascend::std::minmax(5, 5);
    expect_eq("ascend::std::minmax(5, 5).first", res3.first, 5);
    expect_eq("ascend::std::minmax(5, 5).second", res3.second, 5);

    return 0;
}
