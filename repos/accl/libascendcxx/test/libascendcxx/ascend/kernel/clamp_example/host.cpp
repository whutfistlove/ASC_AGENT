#include "host.h"

extern "C" void aclrtlaunch_clamp_kernel(uint32_t core_num, void* stream, void* x, void* y, void* z);

void ascend_std_clamp_do(uint32_t core_num, void* stream, uint8_t* x_dev, uint8_t* y_dev, uint8_t* z_dev)
{
    aclrtlaunch_clamp_kernel(core_num, stream, x_dev, y_dev, z_dev);
}
