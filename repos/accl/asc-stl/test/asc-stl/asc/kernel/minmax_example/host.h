#ifndef ASC_STL_TEST_ASC_STL_ASC_KERNEL_MINMAX_EXAMPLE_HOST_H_
#define ASC_STL_TEST_ASC_STL_ASC_KERNEL_MINMAX_EXAMPLE_HOST_H_

#include <cstdint>

void asc_std_minmax_do(uint32_t core_num, void* stream, uint8_t* in0_dev, uint8_t* in1_dev, uint8_t* out0_dev, uint8_t* out1_dev);

#endif  // ASC_STL_TEST_ASC_STL_ASC_KERNEL_MINMAX_EXAMPLE_HOST_H_
