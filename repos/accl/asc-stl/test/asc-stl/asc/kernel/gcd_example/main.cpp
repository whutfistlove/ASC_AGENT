// auto-workload=full (n=16384, cores=8, inputs=2, outputs=1, dtype=int32_t)
#include "acl/acl.h"
#include "host.h"
#include "asc/std/__numeric/gcd.h"
#include <cmath>
#include <cstdlib>
#include <iostream>
#include <vector>

#define CHECK_ACL(call)                                                                   \
    do {                                                                                  \
        aclError err = call;                                                              \
        if (err != ACL_SUCCESS) {                                                         \
            std::cerr << "ACL error: " << err << " at " << __FILE__ << ":" << __LINE__ \
                      << std::endl;                                                       \
            return 1;                                                                      \
        }                                                                                  \
    } while (0)

int main()
{
    const size_t n = 16384;
    const size_t bytes = n * sizeof(int32_t);

    CHECK_ACL(aclInit(nullptr));
    CHECK_ACL(aclrtSetDevice(0));

    void* stream = nullptr;
    CHECK_ACL(aclrtCreateStream(&stream));

    std::vector<int32_t> h_in0(n);
    std::vector<int32_t> h_in1(n);
    std::vector<int32_t> h_out0(n);
    auto& h_x = h_in0;
    auto& h_y = h_in1;
    (void)h_x;
    (void)h_y;
    for (size_t i = 0; i < n; ++i) {
        { h_in0[i] = static_cast<int32_t>((i * 7 + 3) % 199) - 99; h_in1[i] = static_cast<int32_t>((i * 13 + 5) % 199) - 99; }
    }

    void* d_in0 = nullptr;
    void* d_in1 = nullptr;
    void* d_out0 = nullptr;
    CHECK_ACL(aclrtMalloc(&d_in0, bytes, ACL_MEM_MALLOC_HUGE_FIRST));
    CHECK_ACL(aclrtMalloc(&d_in1, bytes, ACL_MEM_MALLOC_HUGE_FIRST));
    CHECK_ACL(aclrtMalloc(&d_out0, bytes, ACL_MEM_MALLOC_HUGE_FIRST));

    CHECK_ACL(aclrtMemcpy(d_in0, bytes, h_in0.data(), bytes, ACL_MEMCPY_HOST_TO_DEVICE));
    CHECK_ACL(aclrtMemcpy(d_in1, bytes, h_in1.data(), bytes, ACL_MEMCPY_HOST_TO_DEVICE));

    asc_std_gcd_do(8, stream, static_cast<uint8_t*>(d_in0), static_cast<uint8_t*>(d_in1), static_cast<uint8_t*>(d_out0));
    CHECK_ACL(aclrtSynchronizeStream(stream));
    CHECK_ACL(aclrtMemcpy(h_out0.data(), bytes, d_out0, bytes, ACL_MEMCPY_DEVICE_TO_HOST));

    long print_samples = 8;
    if (const char* __ps = std::getenv("KERNEL_PRINT_SAMPLES")) {
        if (*__ps) print_samples = std::atol(__ps);
    }
    size_t mismatches = 0;
    for (size_t i = 0; i < n; ++i) {
        int32_t in0_ref = h_in0[i];
        int32_t in1_ref = h_in1[i];
        int32_t x_ref = in0_ref;
        int32_t y_ref = in1_ref;
        (void)x_ref;
        (void)y_ref;
        (void)in0_ref;
        (void)in1_ref;
        int32_t expected0 = (int32_t)0;
        int32_t& expected = expected0;
        (void)expected;
        (void)expected0;
        { int32_t a = (in0_ref < 0) ? -in0_ref : in0_ref; int32_t b = (in1_ref < 0) ? -in1_ref : in1_ref; while (b != 0) { int32_t t = a % b; a = b; b = t; } expected0 = a; }
        int32_t got0 = h_out0[i];
        if (print_samples < 0 || static_cast<long>(i) < print_samples) {
            std::cout << "[kernel][gcd][" << i << "]" << " in0=" << in0_ref << " in1=" << in1_ref
                      << " got=" << got0 << " expected=" << expected0 << std::endl;
        }
        if (got0 != expected0) {
            ++mismatches;
            if (mismatches <= 8) {
                std::cerr << "Mismatch at i=" << i << ", out0, got=" << got0
                          << ", expected=" << expected0 << std::endl;
            }
        }
    }
    std::cout << "[kernel][gcd] checked " << n << " elements, mismatches "
              << mismatches << std::endl;
    if (mismatches != 0) {
        aclrtFree(d_in0);
        aclrtFree(d_in1);
        aclrtFree(d_out0);
        aclrtDestroyStream(stream);
        aclrtResetDevice(0);
        aclFinalize();
        return 2;
    }

    aclrtFree(d_in0);
    aclrtFree(d_in1);
    aclrtFree(d_out0);
    aclrtDestroyStream(stream);
    aclrtResetDevice(0);
    aclFinalize();

    std::cout << "kernel simulation verification passed." << std::endl;
    return 0;
}
