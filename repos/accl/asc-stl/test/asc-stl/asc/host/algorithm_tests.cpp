#include "asc/std/__host_stdlib/algorithm"
#include <iostream>

static int g_failures = 0;

int main()
{
    // This header is a passthrough/umbrella wrapper with no callable symbols.
    // The only verifiable contract is that it compiles cleanly and the header
    // guard macro is defined.
    bool guard_defined = false;
#ifdef ASC_STL_INCLUDE_ASC_STD___HOST_STDLIB_ALGORITHM_
    guard_defined = true;
#endif
    std::cout << "[host][algorithm] Header guard ASC_STL_INCLUDE_ASC_STD___HOST_STDLIB_ALGORITHM_ defined = "
              << (guard_defined ? "true" : "false") << " (expected true) "
              << (guard_defined ? "OK" : "FAIL") << std::endl;
    if (!guard_defined) ++g_failures;

    std::cout << "[host][algorithm] Header asc/std/__host_stdlib/algorithm included OK" << std::endl;

    return g_failures == 0 ? 0 : 1;
}
