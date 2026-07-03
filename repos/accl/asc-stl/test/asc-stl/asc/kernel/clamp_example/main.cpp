// auto-workload=full (n=16384, cores=8, inputs=2, outputs=1, dtype=float)
#include "acl/acl.h"
#include "host.h"
#include "asc/std/__algorithm/clamp.h"
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
    auto& h_x = h_in0;
    auto& h_y = h_in1;
    (void)h_x;
    (void)h_y;
    for (size_t i = 0; i < n; ++i) {
        { h_x[i] = static_cast<float>(i); h_y[i] = static_cast<float>(i * 2); }
    }

    void* d_in0 = nullptr;
    void* d_in1 = nullptr;
    void* d_out0 = nullptr;
    CHECK_ACL(aclrtMalloc(&d_in0, bytes, ACL_MEM_MALLOC_HUGE_FIRST));
    CHECK_ACL(aclrtMalloc(&d_in1, bytes, ACL_MEM_MALLOC_HUGE_FIRST));
    CHECK_ACL(aclrtMalloc(&d_out0, bytes, ACL_MEM_MALLOC_HUGE_FIRST));

    CHECK_ACL(aclrtMemcpy(d_in0, bytes, h_in0.data(), bytes, ACL_MEMCPY_HOST_TO_DEVICE));
    CHECK_ACL(aclrtMemcpy(d_in1, bytes, h_in1.data(), bytes, ACL_MEMCPY_HOST_TO_DEVICE));

    asc_std_clamp_do(8, stream, static_cast<uint8_t*>(d_in0), static_cast<uint8_t*>(d_in1), static_cast<uint8_t*>(d_out0));
    CHECK_ACL(aclrtSynchronizeStream(stream));
    CHECK_ACL(aclrtMemcpy(h_out0.data(), bytes, d_out0, bytes, ACL_MEMCPY_DEVICE_TO_HOST));

    std::cout << "[kernel][clamp][SMOKE-ONLY] no kernel_spec provided: "
              << "build + launch + copy-back smoke only; "
              << "semantic golden check skipped." << std::endl;
    std::cout << "[kernel][clamp] ran " << n << " elements (smoke, no golden check)."
              << std::endl;

    aclrtFree(d_in0);
    aclrtFree(d_in1);
    aclrtFree(d_out0);
    aclrtDestroyStream(stream);
    aclrtResetDevice(0);
    aclFinalize();

    std::cout << "[kernel][clamp] smoke run finished (unverified; provide a kernel_spec for golden check)." << std::endl;
    return 0;
}
