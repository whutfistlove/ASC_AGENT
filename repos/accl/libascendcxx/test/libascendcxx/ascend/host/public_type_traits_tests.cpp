#include "ascend/std/type_traits"

int main()
{
    static_assert(ascend::std::true_type::value, "");
    static_assert(!ascend::std::false_type::value, "");
    static_assert(ascend::std::bool_constant<true>::value, "");
    static_assert(ascend::std::is_same_v<int, int>, "");
    static_assert(!ascend::std::is_same_v<int, long>, "");
    static_assert(ascend::std::is_reference_v<int&>, "");
    static_assert(ascend::std::is_lvalue_reference_v<int&>, "");
    static_assert(ascend::std::is_rvalue_reference_v<int&&>, "");
    static_assert(!ascend::std::is_reference_v<int>, "");
    static_assert(ascend::std::is_same_v<ascend::std::remove_reference_t<int&&>, int>, "");
    static_assert(ascend::std::is_same_v<ascend::std::conditional_t<true, int, long>, int>, "");
    static_assert(ascend::std::is_same_v<ascend::std::conditional_t<false, int, long>, long>, "");
    return 0;
}
