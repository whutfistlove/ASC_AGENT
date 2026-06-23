#include "host.h"

extern "C" void aclrtlaunch_sort3_kernel(uint32_t core_num, void* stream, void* in0, void* in1, void* in2, void* out0, void* out1, void* out2);

void asc_std_sort3_do(uint32_t core_num, void* stream, uint8_t* in0_dev, uint8_t* in1_dev, uint8_t* in2_dev, uint8_t* out0_dev, uint8_t* out1_dev, uint8_t* out2_dev)
{
    aclrtlaunch_sort3_kernel(core_num, stream, in0_dev, in1_dev, in2_dev, out0_dev, out1_dev, out2_dev);
}
