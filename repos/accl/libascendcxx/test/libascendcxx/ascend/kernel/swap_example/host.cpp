#include "host.h"

extern "C" void aclrtlaunch_swap_kernel(uint32_t core_num, void* stream, void* x, void* y, void* z);

void ascend_std_swap_do(uint32_t core_num, void* stream, uint8_t* x_dev, uint8_t* y_dev, uint8_t* z_dev)
{
    aclrtlaunch_swap_kernel(core_num, stream, x_dev, y_dev, z_dev);
}
