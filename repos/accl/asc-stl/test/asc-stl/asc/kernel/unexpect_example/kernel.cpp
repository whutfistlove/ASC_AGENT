// auto-workload=full (n=16384, cores=8, tiles=32x64, inputs=1, outputs=1, dtype=int32_t)
#include "kernel_operator.h"
#include "asc/std/__expected/unexpect.h"

extern "C" __global__ __aicore__ void unexpect_kernel(GM_ADDR in0_gm, GM_ADDR out0_gm)
{
    constexpr int32_t TOTAL_LENGTH = 16384;
    constexpr int32_t CORE_NUM = 8;
    constexpr int32_t BLOCK_LENGTH = TOTAL_LENGTH / CORE_NUM;
    constexpr int32_t TILE_NUM = 32;
    constexpr int32_t TILE_SIZE = 64;

    uint32_t block_id = AscendC::GetBlockIdx();

    AscendC::GlobalTensor<int32_t> in0Gm;
    AscendC::GlobalTensor<int32_t> out0Gm;
    in0Gm.SetGlobalBuffer((__gm__ int32_t*)(in0_gm) + block_id * BLOCK_LENGTH, BLOCK_LENGTH);
    out0Gm.SetGlobalBuffer((__gm__ int32_t*)(out0_gm) + block_id * BLOCK_LENGTH, BLOCK_LENGTH);

    AscendC::TQue<AscendC::TPosition::VECIN, 1> inQueue0;
    AscendC::TQue<AscendC::TPosition::VECOUT, 1> outQueue0;

    AscendC::TPipe pipe;
    pipe.InitBuffer(inQueue0, 1, TILE_SIZE * sizeof(int32_t));
    pipe.InitBuffer(outQueue0, 1, TILE_SIZE * sizeof(int32_t));

    for (int32_t tile = 0; tile < TILE_NUM; ++tile) {
        auto in0Buf = inQueue0.AllocTensor<int32_t>();
        AscendC::DataCopy(in0Buf, in0Gm[tile * TILE_SIZE], TILE_SIZE);
        inQueue0.EnQue(in0Buf);

        auto in0Local = inQueue0.DeQue<int32_t>();
        auto out0Local = outQueue0.AllocTensor<int32_t>();

        for (int32_t i = 0; i < TILE_SIZE; ++i) {
            int32_t in0_val = in0Local.GetValue(i);
            int32_t x_val = in0_val;
            int32_t y_val = (int32_t)0;
            (void)x_val;
            (void)y_val;
            (void)in0_val;
            int32_t out0_val = (int32_t)0;
            int32_t& z_val = out0_val;
            (void)z_val;
            (void)out0_val;
            { asc::std::unexpect_t tag{}; (void)tag; out0_val = in0_val; }
            out0Local.SetValue(i, out0_val);
        }

        outQueue0.EnQue(out0Local);
        inQueue0.FreeTensor(in0Local);

        auto out0Buf = outQueue0.DeQue<int32_t>();
        AscendC::DataCopy(out0Gm[tile * TILE_SIZE], out0Buf, TILE_SIZE);
        outQueue0.FreeTensor(out0Buf);
    }
}
