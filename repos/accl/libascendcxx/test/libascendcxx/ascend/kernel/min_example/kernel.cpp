// auto-workload=full (n=16384, cores=8, tiles=32x64)
#include "kernel_operator.h"
#include "ascend/std/__algorithm/min.h"

extern "C" __global__ __aicore__ void min_kernel(GM_ADDR x_gm, GM_ADDR y_gm, GM_ADDR z_gm)
{
    constexpr int32_t TOTAL_LENGTH = 16384;
    constexpr int32_t CORE_NUM = 8;
    constexpr int32_t BLOCK_LENGTH = TOTAL_LENGTH / CORE_NUM;
    constexpr int32_t TILE_NUM = 32;
    constexpr int32_t TILE_SIZE = 64;

    uint32_t block_id = AscendC::GetBlockIdx();

    AscendC::GlobalTensor<float> xGm, yGm, zGm;
    xGm.SetGlobalBuffer((__gm__ float*)(x_gm) + block_id * BLOCK_LENGTH, BLOCK_LENGTH);
    yGm.SetGlobalBuffer((__gm__ float*)(y_gm) + block_id * BLOCK_LENGTH, BLOCK_LENGTH);
    zGm.SetGlobalBuffer((__gm__ float*)(z_gm) + block_id * BLOCK_LENGTH, BLOCK_LENGTH);

    AscendC::TQue<AscendC::TPosition::VECIN, 1> inQueueX, inQueueY;
    AscendC::TQue<AscendC::TPosition::VECOUT, 1> outQueueZ;

    AscendC::TPipe pipe;
    pipe.InitBuffer(inQueueX, 1, TILE_SIZE * sizeof(float));
    pipe.InitBuffer(inQueueY, 1, TILE_SIZE * sizeof(float));
    pipe.InitBuffer(outQueueZ, 1, TILE_SIZE * sizeof(float));

    for (int32_t tile = 0; tile < TILE_NUM; ++tile) {
        auto xBuf = inQueueX.AllocTensor<float>();
        auto yBuf = inQueueY.AllocTensor<float>();
        AscendC::DataCopy(xBuf, xGm[tile * TILE_SIZE], TILE_SIZE);
        AscendC::DataCopy(yBuf, yGm[tile * TILE_SIZE], TILE_SIZE);
        inQueueX.EnQue(xBuf);
        inQueueY.EnQue(yBuf);

        auto xLocal = inQueueX.DeQue<float>();
        auto yLocal = inQueueY.DeQue<float>();
        auto zLocal = outQueueZ.AllocTensor<float>();

        for (int32_t i = 0; i < TILE_SIZE; ++i) {
            float x_val = xLocal.GetValue(i);
            float y_val = yLocal.GetValue(i);
            float z_val = ascend::std::min(x_val, y_val);
            zLocal.SetValue(i, z_val);
        }

        outQueueZ.EnQue(zLocal);
        inQueueX.FreeTensor(xLocal);
        inQueueY.FreeTensor(yLocal);

        auto zBuf = outQueueZ.DeQue<float>();
        AscendC::DataCopy(zGm[tile * TILE_SIZE], zBuf, TILE_SIZE);
        outQueueZ.FreeTensor(zBuf);
    }
}
