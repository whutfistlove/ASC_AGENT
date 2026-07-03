#include "asc/std/__host_stdlib/time.h"
#include <iostream>
#include <cstring>

static int g_failures = 0;

static void expect_true(const char* expr, bool cond)
{
    std::cout << "[host][time] " << expr << " = " << (cond ? "true" : "false")
              << " (expected true) " << (cond ? "OK" : "FAIL") << std::endl;
    if (!cond) ++g_failures;
}

template <typename T>
static void expect_eq(const char* expr, T got, T expected)
{
    bool ok = (got == expected);
    std::cout << "[host][time] " << expr << " = " << got
              << " (expected " << expected << ") " << (ok ? "OK" : "FAIL") << std::endl;
    if (!ok) ++g_failures;
}

int main()
{
    // 1. CLOCKS_PER_SEC is defined (comes from <time.h>)
    expect_true("CLOCKS_PER_SEC > 0", CLOCKS_PER_SEC > 0);

    // 2. clock() is available and returns a non-negative value (or -1 on error)
    {
        clock_t c = clock();
        expect_true("clock() >= -1", c >= (clock_t)-1);
    }

    // 3. time() is available and returns a positive epoch time
    {
        time_t t = time(nullptr);
        expect_true("time(nullptr) > 0", t > (time_t)0);
    }

    // 4. difftime() computes correct difference
    {
        time_t t1 = 1000;
        time_t t2 = 2000;
        double diff = difftime(t2, t1);
        expect_eq("difftime(2000, 1000)", diff, 1000.0);
    }

    // 5. struct tm and mktime() are available
    {
        struct tm tmbuf = {};
        tmbuf.tm_year = 124;  // 2024 - 1900
        tmbuf.tm_mon  = 0;    // January
        tmbuf.tm_mday = 1;
        tmbuf.tm_hour = 0;
        tmbuf.tm_min  = 0;
        tmbuf.tm_sec  = 0;
        time_t result = mktime(&tmbuf);
        expect_true("mktime() != -1 for valid date", result != (time_t)-1);
    }

    // 6. ctime() is available and returns a non-null string
    {
        time_t now = time(nullptr);
        char* ct = ctime(&now);
        expect_true("ctime(&now) != nullptr", ct != nullptr);
    }

    // 7. asctime() is available
    {
        struct tm tmbuf2 = {};
        tmbuf2.tm_year = 124;
        tmbuf2.tm_mon  = 5;
        tmbuf2.tm_mday = 15;
        tmbuf2.tm_hour = 12;
        tmbuf2.tm_min  = 0;
        tmbuf2.tm_sec  = 0;
        mktime(&tmbuf2);
        char* asct = asctime(&tmbuf2);
        expect_true("asctime(&tmbuf2) != nullptr", asct != nullptr);
    }

    // 8. gmtime() is available
    {
        time_t now = time(nullptr);
        struct tm* gmt = gmtime(&now);
        expect_true("gmtime(&now) != nullptr", gmt != nullptr);
    }

    // 9. localtime() is available
    {
        time_t now = time(nullptr);
        struct tm* lct = localtime(&now);
        expect_true("localtime(&now) != nullptr", lct != nullptr);
    }

    // 10. strftime() is available and produces output
    {
        time_t now = time(nullptr);
        struct tm* lct = localtime(&now);
        char buf[64] = {};
        size_t n = strftime(buf, sizeof(buf), "%Y", lct);
        expect_true("strftime returns > 0", n > 0);
    }

    // 11. Header compiled without C-macro #error
    //     (If any time functions were defined as macros, the header would have #error'd)
    expect_true("header compiled without C-macro #error", true);

    return g_failures == 0 ? 0 : 1;
}
