#include "host.h"

extern "C" void aclrtlaunch_any_of_kernel(uint32_t core_num, void* stream, void* in0, void* out0);

void asc_std_any_of_do(uint32_t core_num, void* stream, uint8_t* in0_dev, uint8_t* out0_dev)
{
    aclrtlaunch_any_of_kernel(core_num, stream, in0_dev, out0_dev);
}
