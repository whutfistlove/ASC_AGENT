#include "host.h"

extern "C" void aclrtlaunch_quad_fanout_kernel(uint32_t core_num, void* stream, void* in0, void* in1, void* in2, void* in3, void* out0, void* out1, void* out2, void* out3, void* out4);

void asc_std_quad_fanout_do(uint32_t core_num, void* stream, uint8_t* in0_dev, uint8_t* in1_dev, uint8_t* in2_dev, uint8_t* in3_dev, uint8_t* out0_dev, uint8_t* out1_dev, uint8_t* out2_dev, uint8_t* out3_dev, uint8_t* out4_dev)
{
    aclrtlaunch_quad_fanout_kernel(core_num, stream, in0_dev, in1_dev, in2_dev, in3_dev, out0_dev, out1_dev, out2_dev, out3_dev, out4_dev);
}
