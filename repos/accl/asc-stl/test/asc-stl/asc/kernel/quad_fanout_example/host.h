#ifndef ASC_STL_TEST_ASC_STL_ASC_KERNEL_QUAD_FANOUT_EXAMPLE_HOST_H_
#define ASC_STL_TEST_ASC_STL_ASC_KERNEL_QUAD_FANOUT_EXAMPLE_HOST_H_

#include <cstdint>

void asc_std_quad_fanout_do(uint32_t core_num, void* stream, uint8_t* in0_dev, uint8_t* in1_dev, uint8_t* in2_dev, uint8_t* in3_dev, uint8_t* out0_dev, uint8_t* out1_dev, uint8_t* out2_dev, uint8_t* out3_dev, uint8_t* out4_dev);

#endif  // ASC_STL_TEST_ASC_STL_ASC_KERNEL_QUAD_FANOUT_EXAMPLE_HOST_H_
