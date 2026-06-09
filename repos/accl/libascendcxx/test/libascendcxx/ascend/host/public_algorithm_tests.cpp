#include "ascend/std/algorithm"

#include <iostream>

struct ReverseLess {
    constexpr bool operator()(int lhs, int rhs) const
    {
        return rhs < lhs;
    }
};

int main()
{
    int failures = 0;

    int low = 2;
    int mid = 5;
    int high = 9;

    if (&ascend::std::max(low, high) != &high) {
        ++failures;
        std::cout << "[host][public_algorithm] max failed" << std::endl;
    }
    if (&ascend::std::min(low, high) != &low) {
        ++failures;
        std::cout << "[host][public_algorithm] min failed" << std::endl;
    }
    if (&ascend::std::clamp(mid, low, high) != &mid) {
        ++failures;
        std::cout << "[host][public_algorithm] clamp middle failed" << std::endl;
    }
    if (&ascend::std::clamp(1, low, high) != &low) {
        ++failures;
        std::cout << "[host][public_algorithm] clamp low failed" << std::endl;
    }
    if (&ascend::std::clamp(10, low, high) != &high) {
        ++failures;
        std::cout << "[host][public_algorithm] clamp high failed" << std::endl;
    }

    auto ordered = ascend::std::minmax(high, low);
    if (&ordered.first != &low || &ordered.second != &high) {
        ++failures;
        std::cout << "[host][public_algorithm] minmax failed" << std::endl;
    }

    auto reverse_ordered = ascend::std::minmax(high, low, ReverseLess());
    if (&reverse_ordered.first != &high || &reverse_ordered.second != &low) {
        ++failures;
        std::cout << "[host][public_algorithm] minmax comparator failed" << std::endl;
    }

    int left = 11;
    int right = 23;
    ascend::std::swap(left, right);
    if (left != 23 || right != 11) {
        ++failures;
        std::cout << "[host][public_algorithm] swap failed" << std::endl;
    }

    int lhs[2] = {1, 2};
    int rhs[2] = {3, 4};
    ascend::std::swap(lhs, rhs);
    if (lhs[0] != 3 || lhs[1] != 4 || rhs[0] != 1 || rhs[1] != 2) {
        ++failures;
        std::cout << "[host][public_algorithm] array swap failed" << std::endl;
    }

    constexpr int cmax = ascend::std::max(4, 8);
    constexpr int cmin = ascend::std::min(4, 8);
    static_assert(cmax == 8, "");
    static_assert(cmin == 4, "");

    return failures == 0 ? 0 : 1;
}
