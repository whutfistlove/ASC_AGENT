// auto-workload=full (n=16384, cores=8, inputs=4, outputs=5)
#include "acl/acl.h"
#include "host.h"
#include "ascend/std/__algorithm/quad_fanout.h"
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
    std::vector<float> h_in2(n);
    std::vector<float> h_in3(n);
    std::vector<float> h_out0(n);
    std::vector<float> h_out1(n);
    std::vector<float> h_out2(n);
    std::vector<float> h_out3(n);
    std::vector<float> h_out4(n);
    auto& h_x = h_in0;
    auto& h_y = h_in1;
    (void)h_x;
    (void)h_y;
    for (size_t i = 0; i < n; ++i) {
        { h_in0[i] = static_cast<float>(i % 11) - 5.0f; h_in1[i] = static_cast<float>((i * 3) % 13) - 6.0f; h_in2[i] = static_cast<float>((i * 7) % 17) - 8.0f; h_in3[i] = static_cast<float>((i * 11) % 19) - 9.0f; }
    }

    void* d_in0 = nullptr;
    void* d_in1 = nullptr;
    void* d_in2 = nullptr;
    void* d_in3 = nullptr;
    void* d_out0 = nullptr;
    void* d_out1 = nullptr;
    void* d_out2 = nullptr;
    void* d_out3 = nullptr;
    void* d_out4 = nullptr;
    CHECK_ACL(aclrtMalloc(&d_in0, bytes, ACL_MEM_MALLOC_HUGE_FIRST));
    CHECK_ACL(aclrtMalloc(&d_in1, bytes, ACL_MEM_MALLOC_HUGE_FIRST));
    CHECK_ACL(aclrtMalloc(&d_in2, bytes, ACL_MEM_MALLOC_HUGE_FIRST));
    CHECK_ACL(aclrtMalloc(&d_in3, bytes, ACL_MEM_MALLOC_HUGE_FIRST));
    CHECK_ACL(aclrtMalloc(&d_out0, bytes, ACL_MEM_MALLOC_HUGE_FIRST));
    CHECK_ACL(aclrtMalloc(&d_out1, bytes, ACL_MEM_MALLOC_HUGE_FIRST));
    CHECK_ACL(aclrtMalloc(&d_out2, bytes, ACL_MEM_MALLOC_HUGE_FIRST));
    CHECK_ACL(aclrtMalloc(&d_out3, bytes, ACL_MEM_MALLOC_HUGE_FIRST));
    CHECK_ACL(aclrtMalloc(&d_out4, bytes, ACL_MEM_MALLOC_HUGE_FIRST));

    CHECK_ACL(aclrtMemcpy(d_in0, bytes, h_in0.data(), bytes, ACL_MEMCPY_HOST_TO_DEVICE));
    CHECK_ACL(aclrtMemcpy(d_in1, bytes, h_in1.data(), bytes, ACL_MEMCPY_HOST_TO_DEVICE));
    CHECK_ACL(aclrtMemcpy(d_in2, bytes, h_in2.data(), bytes, ACL_MEMCPY_HOST_TO_DEVICE));
    CHECK_ACL(aclrtMemcpy(d_in3, bytes, h_in3.data(), bytes, ACL_MEMCPY_HOST_TO_DEVICE));

    ascend_std_quad_fanout_do(8, stream, static_cast<uint8_t*>(d_in0), static_cast<uint8_t*>(d_in1), static_cast<uint8_t*>(d_in2), static_cast<uint8_t*>(d_in3), static_cast<uint8_t*>(d_out0), static_cast<uint8_t*>(d_out1), static_cast<uint8_t*>(d_out2), static_cast<uint8_t*>(d_out3), static_cast<uint8_t*>(d_out4));
    CHECK_ACL(aclrtSynchronizeStream(stream));
    CHECK_ACL(aclrtMemcpy(h_out0.data(), bytes, d_out0, bytes, ACL_MEMCPY_DEVICE_TO_HOST));
    CHECK_ACL(aclrtMemcpy(h_out1.data(), bytes, d_out1, bytes, ACL_MEMCPY_DEVICE_TO_HOST));
    CHECK_ACL(aclrtMemcpy(h_out2.data(), bytes, d_out2, bytes, ACL_MEMCPY_DEVICE_TO_HOST));
    CHECK_ACL(aclrtMemcpy(h_out3.data(), bytes, d_out3, bytes, ACL_MEMCPY_DEVICE_TO_HOST));
    CHECK_ACL(aclrtMemcpy(h_out4.data(), bytes, d_out4, bytes, ACL_MEMCPY_DEVICE_TO_HOST));

    constexpr float eps = 1e-5f;
    // 逐元素打印多少条用例：环境变量 KERNEL_PRINT_SAMPLES 控制
    // （默认 8；设为负数则打印全部；0 则不逐条打印，只留汇总）。
    long print_samples = 8;
    if (const char* __ps = std::getenv("KERNEL_PRINT_SAMPLES")) {
        if (*__ps) print_samples = std::atol(__ps);
    }
    size_t mismatches = 0;
    for (size_t i = 0; i < n; ++i) {
        float in0_ref = h_in0[i];
        float in1_ref = h_in1[i];
        float in2_ref = h_in2[i];
        float in3_ref = h_in3[i];
        float x_ref = in0_ref;
        float y_ref = in1_ref;
        (void)x_ref;
        (void)y_ref;
        (void)in0_ref;
        (void)in1_ref;
        (void)in2_ref;
        (void)in3_ref;
        float expected0 = 0.0f;
        float expected1 = 0.0f;
        float expected2 = 0.0f;
        float expected3 = 0.0f;
        float expected4 = 0.0f;
        float& expected = expected0;
        (void)expected;
        (void)expected0;
        (void)expected1;
        (void)expected2;
        (void)expected3;
        (void)expected4;
        { expected0 = in0_ref + in1_ref; expected1 = in1_ref + in2_ref; expected2 = in2_ref + in3_ref; expected3 = in0_ref - in3_ref; expected4 = in0_ref + in1_ref + in2_ref + in3_ref; }
        float got0 = h_out0[i];
        if (print_samples < 0 || static_cast<long>(i) < print_samples) {
            std::cout << "[kernel][quad_fanout][" << i << "][out0]" << " in0=" << in0_ref << " in1=" << in1_ref << " in2=" << in2_ref << " in3=" << in3_ref
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
            std::cout << "[kernel][quad_fanout][" << i << "][out1]" << " in0=" << in0_ref << " in1=" << in1_ref << " in2=" << in2_ref << " in3=" << in3_ref
                      << " got=" << got1 << " expected=" << expected1 << std::endl;
        }
        if (std::abs(got1 - expected1) > eps) {
            ++mismatches;
            if (mismatches <= 8) {
                std::cerr << "Mismatch at i=" << i << ", out1, got=" << got1
                          << ", expected=" << expected1 << std::endl;
            }
        }

        float got2 = h_out2[i];
        if (print_samples < 0 || static_cast<long>(i) < print_samples) {
            std::cout << "[kernel][quad_fanout][" << i << "][out2]" << " in0=" << in0_ref << " in1=" << in1_ref << " in2=" << in2_ref << " in3=" << in3_ref
                      << " got=" << got2 << " expected=" << expected2 << std::endl;
        }
        if (std::abs(got2 - expected2) > eps) {
            ++mismatches;
            if (mismatches <= 8) {
                std::cerr << "Mismatch at i=" << i << ", out2, got=" << got2
                          << ", expected=" << expected2 << std::endl;
            }
        }

        float got3 = h_out3[i];
        if (print_samples < 0 || static_cast<long>(i) < print_samples) {
            std::cout << "[kernel][quad_fanout][" << i << "][out3]" << " in0=" << in0_ref << " in1=" << in1_ref << " in2=" << in2_ref << " in3=" << in3_ref
                      << " got=" << got3 << " expected=" << expected3 << std::endl;
        }
        if (std::abs(got3 - expected3) > eps) {
            ++mismatches;
            if (mismatches <= 8) {
                std::cerr << "Mismatch at i=" << i << ", out3, got=" << got3
                          << ", expected=" << expected3 << std::endl;
            }
        }

        float got4 = h_out4[i];
        if (print_samples < 0 || static_cast<long>(i) < print_samples) {
            std::cout << "[kernel][quad_fanout][" << i << "][out4]" << " in0=" << in0_ref << " in1=" << in1_ref << " in2=" << in2_ref << " in3=" << in3_ref
                      << " got=" << got4 << " expected=" << expected4 << std::endl;
        }
        if (std::abs(got4 - expected4) > eps) {
            ++mismatches;
            if (mismatches <= 8) {
                std::cerr << "Mismatch at i=" << i << ", out4, got=" << got4
                          << ", expected=" << expected4 << std::endl;
            }
        }
    }
    std::cout << "[kernel][quad_fanout] checked " << n << " elements, mismatches "
              << mismatches << std::endl;
    if (mismatches != 0) {
        aclrtFree(d_in0);
        aclrtFree(d_in1);
        aclrtFree(d_in2);
        aclrtFree(d_in3);
        aclrtFree(d_out0);
        aclrtFree(d_out1);
        aclrtFree(d_out2);
        aclrtFree(d_out3);
        aclrtFree(d_out4);
        aclrtDestroyStream(stream);
        aclrtResetDevice(0);
        aclFinalize();
        return 2;
    }

    aclrtFree(d_in0);
    aclrtFree(d_in1);
    aclrtFree(d_in2);
    aclrtFree(d_in3);
    aclrtFree(d_out0);
    aclrtFree(d_out1);
    aclrtFree(d_out2);
    aclrtFree(d_out3);
    aclrtFree(d_out4);
    aclrtDestroyStream(stream);
    aclrtResetDevice(0);
    aclFinalize();

    std::cout << "kernel simulation verification passed." << std::endl;
    return 0;
}
