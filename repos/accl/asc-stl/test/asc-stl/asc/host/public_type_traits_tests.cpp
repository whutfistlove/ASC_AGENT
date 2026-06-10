#include "asc/std/type_traits"

int main()
{
    static_assert(asc::std::true_type::value, "");
    static_assert(!asc::std::false_type::value, "");
    static_assert(asc::std::bool_constant<true>::value, "");
    static_assert(asc::std::is_same_v<int, int>, "");
    static_assert(!asc::std::is_same_v<int, long>, "");
    static_assert(asc::std::is_reference_v<int&>, "");
    static_assert(asc::std::is_lvalue_reference_v<int&>, "");
    static_assert(asc::std::is_rvalue_reference_v<int&&>, "");
    static_assert(!asc::std::is_reference_v<int>, "");
    static_assert(asc::std::is_same_v<asc::std::remove_reference_t<int&&>, int>, "");
    static_assert(asc::std::is_same_v<asc::std::conditional_t<true, int, long>, int>, "");
    static_assert(asc::std::is_same_v<asc::std::conditional_t<false, int, long>, long>, "");
    return 0;
}
