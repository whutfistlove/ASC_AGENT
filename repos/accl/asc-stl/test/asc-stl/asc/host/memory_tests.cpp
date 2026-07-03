#include "asc/std/__host_stdlib/memory"
#include <iostream>
#include <memory>

static int g_failures = 0;

template <typename T>
static void expect_eq(const char* expr, T got, T expected)
{
    bool ok = (got == expected);
    std::cout << "[host][memory] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

static void expect_true(const char* expr, bool cond)
{
    std::cout << "[host][memory] " << expr << " = " << (cond ? "true" : "false")
              << " (expected true) " << (cond ? "OK" : "FAIL") << std::endl;
    if (!cond) ++g_failures;
}

int main()
{
    // Test that std::unique_ptr is available via the included <memory>
    {
        std::unique_ptr<int> p = std::make_unique<int>(42);
        expect_true("unique_ptr bool", static_cast<bool>(p));
        expect_eq("unique_ptr value", *p, 42);
    }

    // Test that std::shared_ptr is available
    {
        std::shared_ptr<int> p = std::make_shared<int>(99);
        expect_true("shared_ptr bool", static_cast<bool>(p));
        expect_eq("shared_ptr value", *p, 99);
        expect_eq("shared_ptr use_count", static_cast<int>(p.use_count()), 1);
    }

    // Test shared_ptr copy / use_count
    {
        auto p1 = std::make_shared<int>(7);
        auto p2 = p1;
        expect_eq("shared_ptr copy use_count", static_cast<int>(p1.use_count()), 2);
        expect_eq("shared_ptr copy value via p2", *p2, 7);
    }

    // Test unique_ptr reset
    {
        std::unique_ptr<int> p = std::make_unique<int>(10);
        p.reset(new int(20));
        expect_eq("unique_ptr after reset", *p, 20);
    }

    // Test unique_ptr release
    {
        std::unique_ptr<int> p = std::make_unique<int>(55);
        int* raw = p.release();
        expect_true("unique_ptr empty after release", !p);
        expect_eq("unique_ptr released value", *raw, 55);
        delete raw;
    }

    return g_failures == 0 ? 0 : 1;
}
