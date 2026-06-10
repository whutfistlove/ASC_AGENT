// auto-workload=fast (n=64, cores=1, inputs=2, outputs=1, dtype=float)
#include "acl/acl.h"
#include "host.h"
#include "asc/std/__utility/swap.h"
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
    const size_t n = 64;
    const size_t bytes = n * sizeof(float);

    CHECK_ACL(aclInit(nullptr));
    CHECK_ACL(aclrtSetDevice(0));

    void* stream = nullptr;
    CHECK_ACL(aclrtCreateStream(&stream));

    std::vector<float> h_in0(n);
    std::vector<float> h_in1(n);
    std::vector<float> h_out0(n);
    auto& h_x = h_in0;
    auto& h_y = h_in1;
    (void)h_x;
    (void)h_y;
    for (size_t i = 0; i < n; ++i) {
        { h_x[i] = static_cast<float>(i % 100) - 50.0f; h_y[i] = static_cast<float>((i * 7 + 13) % 100) - 50.0f; }
    }

    void* d_in0 = nullptr;
    void* d_in1 = nullptr;
    void* d_out0 = nullptr;
    CHECK_ACL(aclrtMalloc(&d_in0, bytes, ACL_MEM_MALLOC_HUGE_FIRST));
    CHECK_ACL(aclrtMalloc(&d_in1, bytes, ACL_MEM_MALLOC_HUGE_FIRST));
    CHECK_ACL(aclrtMalloc(&d_out0, bytes, ACL_MEM_MALLOC_HUGE_FIRST));

    CHECK_ACL(aclrtMemcpy(d_in0, bytes, h_in0.data(), bytes, ACL_MEMCPY_HOST_TO_DEVICE));
    CHECK_ACL(aclrtMemcpy(d_in1, bytes, h_in1.data(), bytes, ACL_MEMCPY_HOST_TO_DEVICE));

    asc_std_swap_do(1, stream, static_cast<uint8_t*>(d_in0), static_cast<uint8_t*>(d_in1), static_cast<uint8_t*>(d_out0));
    CHECK_ACL(aclrtSynchronizeStream(stream));
    CHECK_ACL(aclrtMemcpy(h_out0.data(), bytes, d_out0, bytes, ACL_MEMCPY_DEVICE_TO_HOST));

    constexpr float eps = (float)1e-5;
    long print_samples = 8;
    if (const char* __ps = std::getenv("KERNEL_PRINT_SAMPLES")) {
        if (*__ps) print_samples = std::atol(__ps);
    }
    size_t mismatches = 0;
    for (size_t i = 0; i < n; ++i) {
        float in0_ref = h_in0[i];
        float in1_ref = h_in1[i];
        float x_ref = in0_ref;
        float y_ref = in1_ref;
        (void)x_ref;
        (void)y_ref;
        (void)in0_ref;
        (void)in1_ref;
        float expected0 = (float)0;
        float& expected = expected0;
        (void)expected;
        (void)expected0;
        { expected = y_ref; }
        float got0 = h_out0[i];
        if (print_samples < 0 || static_cast<long>(i) < print_samples) {
            std::cout << "[kernel][swap][" << i << "]" << " in0=" << in0_ref << " in1=" << in1_ref
                      << " got=" << got0 << " expected=" << expected0 << std::endl;
        }
        if (std::abs(got0 - expected0) > eps) {
            ++mismatches;
            if (mismatches <= 8) {
                std::cerr << "Mismatch at i=" << i << ", out0, got=" << got0
                          << ", expected=" << expected0 << std::endl;
            }
        }
    }
    std::cout << "[kernel][swap] checked " << n << " elements, mismatches "
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
