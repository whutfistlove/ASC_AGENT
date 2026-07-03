#include "asc/std/__host_stdlib/new"
#include <iostream>

static int g_failures = 0;

static void expect_true(const char* expr, bool cond)
{
    std::cout << "[host][new] " << expr << " = " << (cond ? "true" : "false")
              << " (expected true) " << (cond ? "OK" : "FAIL") << std::endl;
    if (!cond) ++g_failures;
}

int main()
{
    // Test 1: ASC_DEVICE_CODE must NOT be defined on host side
    expect_true("ASC_DEVICE_CODE is not defined on host",
#if defined(ASC_DEVICE_CODE)
                false
#else
                true
#endif
    );

    // Test 2: std::nothrow is available via the included <new>
    expect_true("std::nothrow is available", true);
    (void)std::nothrow;

    // Test 3: operator new(std::nothrow) is available via <new>
    void* p = ::operator new(1, std::nothrow);
    expect_true("::operator new(1, std::nothrow) returns non-null", p != nullptr);
    ::operator delete(p);

    // Test 4: operator new with alignment (C++17) via <new>
    void* p2 = ::operator new(8, static_cast<std::align_val_t>(16), std::nothrow);
    expect_true("aligned ::operator new returns non-null", p2 != nullptr);
    ::operator delete(p2, static_cast<std::align_val_t>(16));

    return g_failures == 0 ? 0 : 1;
}
