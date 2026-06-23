#include "host.h"

extern "C" void aclrtlaunch_all_of_kernel(uint32_t core_num, void* stream, void* in0, void* in1, void* in2, void* in3, void* out0);

void asc_std_all_of_do(uint32_t core_num, void* stream, uint8_t* in0_dev, uint8_t* in1_dev, uint8_t* in2_dev, uint8_t* in3_dev, uint8_t* out0_dev)
{
    aclrtlaunch_all_of_kernel(core_num, stream, in0_dev, in1_dev, in2_dev, in3_dev, out0_dev);
}
