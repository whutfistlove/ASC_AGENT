#include "asc/std/utility"

#include <iostream>

struct MoveOnly {
    int value;

    explicit constexpr MoveOnly(int v) : value(v) {}
    MoveOnly(const MoveOnly&) = delete;
    MoveOnly& operator=(const MoveOnly&) = delete;

    constexpr MoveOnly(MoveOnly&& other) : value(other.value)
    {
        other.value = -1;
    }

    constexpr MoveOnly& operator=(MoveOnly&& other)
    {
        value = other.value;
        other.value = -1;
        return *this;
    }
};

constexpr int category(int&)
{
    return 1;
}

constexpr int category(int&&)
{
    return 2;
}

template <class T>
constexpr int forward_category(T&& value)
{
    return category(asc::std::forward<T>(value));
}

int main()
{
    int failures = 0;

    int value = 3;
    if (forward_category(value) != 1 || forward_category(3) != 2) {
        ++failures;
        std::cout << "[host][public_utility] forward failed" << std::endl;
    }

    MoveOnly source(7);
    MoveOnly destination(asc::std::move(source));
    if (destination.value != 7 || source.value != -1) {
        ++failures;
        std::cout << "[host][public_utility] move failed" << std::endl;
    }

    asc::std::pair<int, int> values(4, 9);
    if (values.first != 4 || values.second != 9) {
        ++failures;
        std::cout << "[host][public_utility] pair failed" << std::endl;
    }

    auto made = asc::std::make_pair(5, 12);
    if (made.first != 5 || made.second != 12) {
        ++failures;
        std::cout << "[host][public_utility] make_pair failed" << std::endl;
    }

    int left = 1;
    int right = 2;
    asc::std::swap(left, right);
    if (left != 2 || right != 1) {
        ++failures;
        std::cout << "[host][public_utility] swap failed" << std::endl;
    }

    return failures == 0 ? 0 : 1;
}
