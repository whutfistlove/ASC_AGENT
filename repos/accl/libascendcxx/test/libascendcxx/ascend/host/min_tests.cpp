#include "ascend/std/__algorithm/min.h"
#include <cassert>

void test_min_basic()
{
    assert(ascend::std::min(1, 2) == 1);
    assert(ascend::std::min(5.0f, 3.0f) == 3.0f);
}

int main()
{
    test_min_basic();
    return 0;
}
