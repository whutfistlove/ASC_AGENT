// auto-workload=full (n=16384, cores=8)
#include "acl/acl.h"
#include "host.h"
#include "ascend/std/__algorithm/clamp.h"
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

    std::vector<float> h_x(n), h_y(n), h_z(n);
    for (size_t i = 0; i < n; ++i) {
        { h_x[i] = static_cast<float>(i % 200) - 50.0f; }
    }

    void *d_x = nullptr, *d_y = nullptr, *d_z = nullptr;
    CHECK_ACL(aclrtMalloc(&d_x, bytes, ACL_MEM_MALLOC_HUGE_FIRST));
    CHECK_ACL(aclrtMalloc(&d_y, bytes, ACL_MEM_MALLOC_HUGE_FIRST));
    CHECK_ACL(aclrtMalloc(&d_z, bytes, ACL_MEM_MALLOC_HUGE_FIRST));

    CHECK_ACL(aclrtMemcpy(d_x, bytes, h_x.data(), bytes, ACL_MEMCPY_HOST_TO_DEVICE));
    CHECK_ACL(aclrtMemcpy(d_y, bytes, h_y.data(), bytes, ACL_MEMCPY_HOST_TO_DEVICE));

    ascend_std_clamp_do(8, stream, static_cast<uint8_t*>(d_x), static_cast<uint8_t*>(d_y), static_cast<uint8_t*>(d_z));
    CHECK_ACL(aclrtSynchronizeStream(stream));
    CHECK_ACL(aclrtMemcpy(h_z.data(), bytes, d_z, bytes, ACL_MEMCPY_DEVICE_TO_HOST));

    constexpr float eps = 1e-5f;
    // 逐元素打印多少条用例：环境变量 KERNEL_PRINT_SAMPLES 控制
    // （默认 8；设为负数则打印全部；0 则不逐条打印，只留汇总）。
    long print_samples = 8;
    if (const char* __ps = std::getenv("KERNEL_PRINT_SAMPLES")) {
        if (*__ps) print_samples = std::atol(__ps);
    }
    size_t mismatches = 0;
    for (size_t i = 0; i < n; ++i) {
        float x_ref = h_x[i];
        float y_ref = h_y[i];
        (void)x_ref;
        (void)y_ref;
        float expected = 0.0f;
        { expected = (x_ref < 10.0f) ? 10.0f : (x_ref > 100.0f ? 100.0f : x_ref); }
        float got = h_z[i];
        if (print_samples < 0 || static_cast<long>(i) < print_samples) {
            std::cout << "[kernel][clamp][" << i << "] x=" << x_ref << " y=" << y_ref
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
    std::cout << "[kernel][clamp] checked " << n << " elements, mismatches "
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
