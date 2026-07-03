#include "host.h"

extern "C" void aclrtlaunch_empty_completion_kernel(uint32_t core_num, void* stream, void* in0, void* out0);

void asc_std_empty_completion_do(uint32_t core_num, void* stream, uint8_t* in0_dev, uint8_t* out0_dev)
{
    aclrtlaunch_empty_completion_kernel(core_num, stream, in0_dev, out0_dev);
}
