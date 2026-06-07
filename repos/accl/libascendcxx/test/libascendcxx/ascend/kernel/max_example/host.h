#ifndef LIBASCENDCXX_TEST_LIBASCENDCXX_ASCEND_KERNEL_MAX_EXAMPLE_HOST_H_
#define LIBASCENDCXX_TEST_LIBASCENDCXX_ASCEND_KERNEL_MAX_EXAMPLE_HOST_H_

#include <cstdint>

void ascend_std_max_do(uint32_t core_num, void* stream, uint8_t* in0_dev, uint8_t* in1_dev, uint8_t* out0_dev);

#endif  // LIBASCENDCXX_TEST_LIBASCENDCXX_ASCEND_KERNEL_MAX_EXAMPLE_HOST_H_
