// auto-workload=full (n=16384, cores=8, inputs=2, outputs=2)
#include "acl/acl.h"
#include "host.h"
#include "ascend/std/__algorithm/minmax.h"
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
    const size_t bytes = n * sizeof(float);

    CHECK_ACL(aclInit(nullptr));
    CHECK_ACL(aclrtSetDevice(0));

    void* stream = nullptr;
    CHECK_ACL(aclrtCreateStream(&stream));

    std::vector<float> h_in0(n);
    std::vector<float> h_in1(n);
    std::vector<float> h_out0(n);
    std::vector<float> h_out1(n);
    auto& h_x = h_in0;
    auto& h_y = h_in1;
    (void)h_x;
    (void)h_y;
    for (size_t i = 0; i < n; ++i) {
        { h_x[i] = static_cast<float>(i % 97) - 40.0f; h_y[i] = static_cast<float>((i * 3) % 97) - 50.0f; }
    }

    void* d_in0 = nullptr;
    void* d_in1 = nullptr;
    void* d_out0 = nullptr;
    void* d_out1 = nullptr;
    CHECK_ACL(aclrtMalloc(&d_in0, bytes, ACL_MEM_MALLOC_HUGE_FIRST));
    CHECK_ACL(aclrtMalloc(&d_in1, bytes, ACL_MEM_MALLOC_HUGE_FIRST));
    CHECK_ACL(aclrtMalloc(&d_out0, bytes, ACL_MEM_MALLOC_HUGE_FIRST));
    CHECK_ACL(aclrtMalloc(&d_out1, bytes, ACL_MEM_MALLOC_HUGE_FIRST));

    CHECK_ACL(aclrtMemcpy(d_in0, bytes, h_in0.data(), bytes, ACL_MEMCPY_HOST_TO_DEVICE));
    CHECK_ACL(aclrtMemcpy(d_in1, bytes, h_in1.data(), bytes, ACL_MEMCPY_HOST_TO_DEVICE));

    ascend_std_minmax_do(8, stream, static_cast<uint8_t*>(d_in0), static_cast<uint8_t*>(d_in1), static_cast<uint8_t*>(d_out0), static_cast<uint8_t*>(d_out1));
    CHECK_ACL(aclrtSynchronizeStream(stream));
    CHECK_ACL(aclrtMemcpy(h_out0.data(), bytes, d_out0, bytes, ACL_MEMCPY_DEVICE_TO_HOST));
    CHECK_ACL(aclrtMemcpy(h_out1.data(), bytes, d_out1, bytes, ACL_MEMCPY_DEVICE_TO_HOST));

    constexpr float eps = 1e-5f;
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
        float expected0 = 0.0f;
        float expected1 = 0.0f;
        float& expected = expected0;
        (void)expected;
        (void)expected0;
        (void)expected1;
        { expected0 = (y_ref < x_ref) ? y_ref : x_ref; expected1 = (y_ref < x_ref) ? x_ref : y_ref; }
        float got0 = h_out0[i];
        if (print_samples < 0 || static_cast<long>(i) < print_samples) {
            std::cout << "[kernel][minmax][" << i << "][out0]" << " in0=" << in0_ref << " in1=" << in1_ref
                      << " got=" << got0 << " expected=" << expected0 << std::endl;
        }
        if (std::abs(got0 - expected0) > eps) {
            ++mismatches;
            if (mismatches <= 8) {
                std::cerr << "Mismatch at i=" << i << ", out0, got=" << got0
                          << ", expected=" << expected0 << std::endl;
            }
        }

        float got1 = h_out1[i];
        if (print_samples < 0 || static_cast<long>(i) < print_samples) {
            std::cout << "[kernel][minmax][" << i << "][out1]" << " in0=" << in0_ref << " in1=" << in1_ref
                      << " got=" << got1 << " expected=" << expected1 << std::endl;
        }
        if (std::abs(got1 - expected1) > eps) {
            ++mismatches;
            if (mismatches <= 8) {
                std::cerr << "Mismatch at i=" << i << ", out1, got=" << got1
                          << ", expected=" << expected1 << std::endl;
            }
        }
    }
    std::cout << "[kernel][minmax] checked " << n << " elements, mismatches "
              << mismatches << std::endl;
    if (mismatches != 0) {
        aclrtFree(d_in0);
        aclrtFree(d_in1);
        aclrtFree(d_out0);
        aclrtFree(d_out1);
        aclrtDestroyStream(stream);
        aclrtResetDevice(0);
        aclFinalize();
        return 2;
    }

    aclrtFree(d_in0);
    aclrtFree(d_in1);
    aclrtFree(d_out0);
    aclrtFree(d_out1);
    aclrtDestroyStream(stream);
    aclrtResetDevice(0);
    aclFinalize();

    std::cout << "kernel simulation verification passed." << std::endl;
    return 0;
}
