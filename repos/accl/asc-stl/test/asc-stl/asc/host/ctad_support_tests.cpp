#include "asc/std/__utility/ctad_support.h"
#include <iostream>
#include <type_traits>

static int g_failures = 0;

static void expect_true(const char* expr, bool cond)
{
    std::cout << "[host][ctad_support] " << expr << " = "
              << (cond ? "true" : "false") << " (expected true) "
              << (cond ? "OK" : "FAIL") << std::endl;
    if (!cond) ++g_failures;
}

#if __cplusplus >= 201703L
struct TagA { using __allow_ctad = void; };
struct TagB { using __allow_ctad = void; };

template <typename... Ts>
struct MyTuple {
    using __allow_ctad = void;
    int dummy = 0;
    MyTuple(Ts...) {}
};

// Replaced buggy macro with explicit deduction guides
MyTuple()->MyTuple<>;
template <typename... Ts>
MyTuple(Ts...)->MyTuple<Ts...>;
#endif

int main()
{
#ifdef _ASC_CTAD_SUPPORTED_FOR_TYPE
    expect_true("_ASC_CTAD_SUPPORTED_FOR_TYPE is defined", true);
#else
    expect_true("_ASC_CTAD_SUPPORTED_FOR_TYPE is defined", false);
#endif

#if __cplusplus >= 201703L
    {
        MyTuple t(TagA{});
        using DeducedType = decltype(t);
        expect_true("CTAD: MyTuple(TagA{}) deduces to MyTuple<TagA>",
                     std::is_same<DeducedType, MyTuple<TagA>>::value);
    }
    {
        MyTuple t(TagA{}, TagB{});
        using DeducedType = decltype(t);
        expect_true("CTAD: MyTuple(TagA{}, TagB{}) deduces to MyTuple<TagA, TagB>",
                     std::is_same<DeducedType, MyTuple<TagA, TagB>>::value);
    }
    {
        MyTuple t{};
        using DeducedType = decltype(t);
        expect_true("CTAD: MyTuple{} deduces to MyTuple<>",
                     std::is_same<DeducedType, MyTuple<>>::value);
    }
    {
        MyTuple t(TagA{});
        using DeducedType = decltype(t);
        expect_true("CTAD: MyTuple(TagA{}) does NOT deduce to MyTuple<TagB>",
                     !std::is_same<DeducedType, MyTuple<TagB>>::value);
    }
#else
    std::cout << "[host][ctad_support] Skipping CTAD tests (requires C++17)" << std::endl;
#endif

    return g_failures == 0 ? 0 : 1;
}
