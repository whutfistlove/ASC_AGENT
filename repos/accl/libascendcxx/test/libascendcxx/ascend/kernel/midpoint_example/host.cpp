#include "host.h"

extern "C" void aclrtlaunch_midpoint_kernel(uint32_t core_num, void* stream, void* in0, void* in1, void* out0);

void ascend_std_midpoint_do(uint32_t core_num, void* stream, uint8_t* in0_dev, uint8_t* in1_dev, uint8_t* out0_dev)
{
    aclrtlaunch_midpoint_kernel(core_num, stream, in0_dev, in1_dev, out0_dev);
}
