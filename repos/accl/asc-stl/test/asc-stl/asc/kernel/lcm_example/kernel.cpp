// auto-workload=fast (n=64, cores=1, tiles=1x64, inputs=2, outputs=1, dtype=int32_t)
#include "kernel_operator.h"
#include "asc/std/__numeric/lcm.h"

extern "C" __global__ __aicore__ void lcm_kernel(GM_ADDR in0_gm, GM_ADDR in1_gm, GM_ADDR out0_gm)
{
    constexpr int32_t TOTAL_LENGTH = 64;
    constexpr int32_t CORE_NUM = 1;
    constexpr int32_t BLOCK_LENGTH = TOTAL_LENGTH / CORE_NUM;
    constexpr int32_t TILE_NUM = 1;
    constexpr int32_t TILE_SIZE = 64;

    uint32_t block_id = AscendC::GetBlockIdx();

    AscendC::GlobalTensor<int32_t> in0Gm;
    AscendC::GlobalTensor<int32_t> in1Gm;
    AscendC::GlobalTensor<int32_t> out0Gm;
    in0Gm.SetGlobalBuffer((__gm__ int32_t*)(in0_gm) + block_id * BLOCK_LENGTH, BLOCK_LENGTH);
    in1Gm.SetGlobalBuffer((__gm__ int32_t*)(in1_gm) + block_id * BLOCK_LENGTH, BLOCK_LENGTH);
    out0Gm.SetGlobalBuffer((__gm__ int32_t*)(out0_gm) + block_id * BLOCK_LENGTH, BLOCK_LENGTH);

    AscendC::TQue<AscendC::TPosition::VECIN, 1> inQueue0;
    AscendC::TQue<AscendC::TPosition::VECIN, 1> inQueue1;
    AscendC::TQue<AscendC::TPosition::VECOUT, 1> outQueue0;

    AscendC::TPipe pipe;
    pipe.InitBuffer(inQueue0, 1, TILE_SIZE * sizeof(int32_t));
    pipe.InitBuffer(inQueue1, 1, TILE_SIZE * sizeof(int32_t));
    pipe.InitBuffer(outQueue0, 1, TILE_SIZE * sizeof(int32_t));

    for (int32_t tile = 0; tile < TILE_NUM; ++tile) {
        auto in0Buf = inQueue0.AllocTensor<int32_t>();
        AscendC::DataCopy(in0Buf, in0Gm[tile * TILE_SIZE], TILE_SIZE);
        inQueue0.EnQue(in0Buf);
        auto in1Buf = inQueue1.AllocTensor<int32_t>();
        AscendC::DataCopy(in1Buf, in1Gm[tile * TILE_SIZE], TILE_SIZE);
        inQueue1.EnQue(in1Buf);

        auto in0Local = inQueue0.DeQue<int32_t>();
        auto in1Local = inQueue1.DeQue<int32_t>();
        auto out0Local = outQueue0.AllocTensor<int32_t>();

        for (int32_t i = 0; i < TILE_SIZE; ++i) {
            int32_t in0_val = in0Local.GetValue(i);
            int32_t in1_val = in1Local.GetValue(i);
            int32_t x_val = in0_val;
            int32_t y_val = in1_val;
            (void)x_val;
            (void)y_val;
            (void)in0_val;
            (void)in1_val;
            int32_t out0_val = (int32_t)0;
            int32_t& z_val = out0_val;
            (void)z_val;
            (void)out0_val;
            { z_val = asc::std::lcm(x_val, y_val); }
            out0Local.SetValue(i, out0_val);
        }

        outQueue0.EnQue(out0Local);
        inQueue0.FreeTensor(in0Local);
        inQueue1.FreeTensor(in1Local);

        auto out0Buf = outQueue0.DeQue<int32_t>();
        AscendC::DataCopy(out0Gm[tile * TILE_SIZE], out0Buf, TILE_SIZE);
        outQueue0.FreeTensor(out0Buf);
    }
}
