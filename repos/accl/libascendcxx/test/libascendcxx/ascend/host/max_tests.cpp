#include "ascend/std/__algorithm/max.h"
#include <cassert>

void test_max_basic()
{
    assert(ascend::std::max(1, 2) == 2);
    assert(ascend::std::max(5.0f, 3.0f) == 5.0f);
}

void test_max_custom_comp()
{
    auto comp = [](int a, int b) { return a < b; };
    assert(ascend::std::max(10, 20, comp) == 20);
}

int main()
{
    test_max_basic();
    test_max_custom_comp();
    return 0;
}
