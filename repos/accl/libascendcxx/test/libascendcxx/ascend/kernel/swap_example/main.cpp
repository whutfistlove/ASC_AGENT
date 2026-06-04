// auto-workload=full (n=16384, cores=8)
#include "acl/acl.h"
#include "host.h"
#include "ascend/std/__algorithm/swap.h"
#include <cmath>
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

    std::vector<float> h_x(n), h_y(n), h_z(n);
    for (size_t i = 0; i < n; ++i) {
        { h_x[i] = static_cast<float>(i % 100) - 50.0f; h_y[i] = static_cast<float>((i * 7 + 13) % 100) - 50.0f; }
    }

    void *d_x = nullptr, *d_y = nullptr, *d_z = nullptr;
    CHECK_ACL(aclrtMalloc(&d_x, bytes, ACL_MEM_MALLOC_HUGE_FIRST));
    CHECK_ACL(aclrtMalloc(&d_y, bytes, ACL_MEM_MALLOC_HUGE_FIRST));
    CHECK_ACL(aclrtMalloc(&d_z, bytes, ACL_MEM_MALLOC_HUGE_FIRST));

    CHECK_ACL(aclrtMemcpy(d_x, bytes, h_x.data(), bytes, ACL_MEMCPY_HOST_TO_DEVICE));
    CHECK_ACL(aclrtMemcpy(d_y, bytes, h_y.data(), bytes, ACL_MEMCPY_HOST_TO_DEVICE));

    ascend_std_swap_do(8, stream, static_cast<uint8_t*>(d_x), static_cast<uint8_t*>(d_y), static_cast<uint8_t*>(d_z));
    CHECK_ACL(aclrtSynchronizeStream(stream));
    CHECK_ACL(aclrtMemcpy(h_z.data(), bytes, d_z, bytes, ACL_MEMCPY_DEVICE_TO_HOST));

    constexpr float eps = 1e-5f;
    const size_t sample = (n < 8) ? n : 8;
    size_t mismatches = 0;
    for (size_t i = 0; i < n; ++i) {
        float x_ref = h_x[i];
        float y_ref = h_y[i];
        (void)x_ref;
        (void)y_ref;
        float expected = 0.0f;
        { expected = y_ref; }
        float got = h_z[i];
        if (i < sample) {
            std::cout << "[kernel][swap][" << i << "] x=" << x_ref << " y=" << y_ref
                      << " got=" << got << " expected=" << expected << std::endl;
        }
        if (std::abs(got - expected) > eps) {
            ++mismatches;
            if (mismatches <= 8) {
                std::cerr << "Mismatch at i=" << i << ", got=" << got
                          << ", expected=" << expected << std::endl;
            }
        }
    }
    std::cout << "[kernel][swap] checked " << n << " elements, mismatches "
              << mismatches << std::endl;
    if (mismatches != 0) {
        aclrtFree(d_x);
        aclrtFree(d_y);
        aclrtFree(d_z);
        aclrtDestroyStream(stream);
        aclrtResetDevice(0);
        aclFinalize();
        return 2;
    }

    aclrtFree(d_x);
    aclrtFree(d_y);
    aclrtFree(d_z);
    aclrtDestroyStream(stream);
    aclrtResetDevice(0);
    aclFinalize();

    std::cout << "kernel simulation verification passed." << std::endl;
    return 0;
}
