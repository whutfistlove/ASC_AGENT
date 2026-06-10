#include "asc/std/functional"

#include <iostream>

int main()
{
    int failures = 0;

    int value = 13;
    auto&& ref = asc::std::identity()(value);
    ref = 21;
    if (value != 21) {
        ++failures;
        std::cout << "[host][public_functional] identity failed" << std::endl;
    }

    if (asc::std::plus<int>()(2, 5) != 7) {
        ++failures;
        std::cout << "[host][public_functional] plus failed" << std::endl;
    }
    if (asc::std::minus<int>()(7, 5) != 2) {
        ++failures;
        std::cout << "[host][public_functional] minus failed" << std::endl;
    }
    if (asc::std::multiplies<int>()(3, 4) != 12) {
        ++failures;
        std::cout << "[host][public_functional] multiplies failed" << std::endl;
    }
    if (asc::std::divides<int>()(12, 3) != 4) {
        ++failures;
        std::cout << "[host][public_functional] divides failed" << std::endl;
    }
    if (asc::std::modulus<int>()(13, 5) != 3) {
        ++failures;
        std::cout << "[host][public_functional] modulus failed" << std::endl;
    }
    if (asc::std::negate<int>()(9) != -9) {
        ++failures;
        std::cout << "[host][public_functional] negate failed" << std::endl;
    }
    if (!asc::std::equal_to<void>()(5, 5)) {
        ++failures;
        std::cout << "[host][public_functional] equal_to failed" << std::endl;
    }
    if (!asc::std::less<void>()(2, 5)) {
        ++failures;
        std::cout << "[host][public_functional] less failed" << std::endl;
    }
    if (!asc::std::greater<void>()(9, 3)) {
        ++failures;
        std::cout << "[host][public_functional] greater failed" << std::endl;
    }

    static_assert(asc::std::__is_identity_v<asc::std::identity>, "");
    constexpr int csum = asc::std::plus<int>()(4, 6);
    static_assert(csum == 10, "");

    return failures == 0 ? 0 : 1;
}
