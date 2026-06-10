// auto-workload=full (n=16384, cores=8, tiles=32x64, inputs=4, outputs=5)
#include "kernel_operator.h"
#include "asc/std/__algorithm/quad_fanout.h"

extern "C" __global__ __aicore__ void quad_fanout_kernel(GM_ADDR in0_gm, GM_ADDR in1_gm, GM_ADDR in2_gm, GM_ADDR in3_gm, GM_ADDR out0_gm, GM_ADDR out1_gm, GM_ADDR out2_gm, GM_ADDR out3_gm, GM_ADDR out4_gm)
{
    constexpr int32_t TOTAL_LENGTH = 16384;
    constexpr int32_t CORE_NUM = 8;
    constexpr int32_t BLOCK_LENGTH = TOTAL_LENGTH / CORE_NUM;
    constexpr int32_t TILE_NUM = 32;
    constexpr int32_t TILE_SIZE = 64;

    uint32_t block_id = AscendC::GetBlockIdx();

    AscendC::GlobalTensor<float> in0Gm;
    AscendC::GlobalTensor<float> in1Gm;
    AscendC::GlobalTensor<float> in2Gm;
    AscendC::GlobalTensor<float> in3Gm;
    AscendC::GlobalTensor<float> out0Gm;
    AscendC::GlobalTensor<float> out1Gm;
    AscendC::GlobalTensor<float> out2Gm;
    AscendC::GlobalTensor<float> out3Gm;
    AscendC::GlobalTensor<float> out4Gm;
    in0Gm.SetGlobalBuffer((__gm__ float*)(in0_gm) + block_id * BLOCK_LENGTH, BLOCK_LENGTH);
    in1Gm.SetGlobalBuffer((__gm__ float*)(in1_gm) + block_id * BLOCK_LENGTH, BLOCK_LENGTH);
    in2Gm.SetGlobalBuffer((__gm__ float*)(in2_gm) + block_id * BLOCK_LENGTH, BLOCK_LENGTH);
    in3Gm.SetGlobalBuffer((__gm__ float*)(in3_gm) + block_id * BLOCK_LENGTH, BLOCK_LENGTH);
    out0Gm.SetGlobalBuffer((__gm__ float*)(out0_gm) + block_id * BLOCK_LENGTH, BLOCK_LENGTH);
    out1Gm.SetGlobalBuffer((__gm__ float*)(out1_gm) + block_id * BLOCK_LENGTH, BLOCK_LENGTH);
    out2Gm.SetGlobalBuffer((__gm__ float*)(out2_gm) + block_id * BLOCK_LENGTH, BLOCK_LENGTH);
    out3Gm.SetGlobalBuffer((__gm__ float*)(out3_gm) + block_id * BLOCK_LENGTH, BLOCK_LENGTH);
    out4Gm.SetGlobalBuffer((__gm__ float*)(out4_gm) + block_id * BLOCK_LENGTH, BLOCK_LENGTH);

    AscendC::TQue<AscendC::TPosition::VECIN, 1> inQueue0;
    AscendC::TQue<AscendC::TPosition::VECIN, 1> inQueue1;
    AscendC::TQue<AscendC::TPosition::VECIN, 1> inQueue2;
    AscendC::TQue<AscendC::TPosition::VECIN, 1> inQueue3;
    AscendC::TQue<AscendC::TPosition::VECOUT, 1> outQueue0;
    AscendC::TQue<AscendC::TPosition::VECOUT, 1> outQueue1;
    AscendC::TQue<AscendC::TPosition::VECOUT, 1> outQueue2;
    AscendC::TQue<AscendC::TPosition::VECOUT, 1> outQueue3;
    AscendC::TQue<AscendC::TPosition::VECOUT, 1> outQueue4;

    AscendC::TPipe pipe;
    pipe.InitBuffer(inQueue0, 1, TILE_SIZE * sizeof(float));
    pipe.InitBuffer(inQueue1, 1, TILE_SIZE * sizeof(float));
    pipe.InitBuffer(inQueue2, 1, TILE_SIZE * sizeof(float));
    pipe.InitBuffer(inQueue3, 1, TILE_SIZE * sizeof(float));
    pipe.InitBuffer(outQueue0, 1, TILE_SIZE * sizeof(float));
    pipe.InitBuffer(outQueue1, 1, TILE_SIZE * sizeof(float));
    pipe.InitBuffer(outQueue2, 1, TILE_SIZE * sizeof(float));
    pipe.InitBuffer(outQueue3, 1, TILE_SIZE * sizeof(float));
    pipe.InitBuffer(outQueue4, 1, TILE_SIZE * sizeof(float));

    for (int32_t tile = 0; tile < TILE_NUM; ++tile) {
        auto in0Buf = inQueue0.AllocTensor<float>();
        AscendC::DataCopy(in0Buf, in0Gm[tile * TILE_SIZE], TILE_SIZE);
        inQueue0.EnQue(in0Buf);
        auto in1Buf = inQueue1.AllocTensor<float>();
        AscendC::DataCopy(in1Buf, in1Gm[tile * TILE_SIZE], TILE_SIZE);
        inQueue1.EnQue(in1Buf);
        auto in2Buf = inQueue2.AllocTensor<float>();
        AscendC::DataCopy(in2Buf, in2Gm[tile * TILE_SIZE], TILE_SIZE);
        inQueue2.EnQue(in2Buf);
        auto in3Buf = inQueue3.AllocTensor<float>();
        AscendC::DataCopy(in3Buf, in3Gm[tile * TILE_SIZE], TILE_SIZE);
        inQueue3.EnQue(in3Buf);

        auto in0Local = inQueue0.DeQue<float>();
        auto in1Local = inQueue1.DeQue<float>();
        auto in2Local = inQueue2.DeQue<float>();
        auto in3Local = inQueue3.DeQue<float>();
        auto out0Local = outQueue0.AllocTensor<float>();
        auto out1Local = outQueue1.AllocTensor<float>();
        auto out2Local = outQueue2.AllocTensor<float>();
        auto out3Local = outQueue3.AllocTensor<float>();
        auto out4Local = outQueue4.AllocTensor<float>();

        for (int32_t i = 0; i < TILE_SIZE; ++i) {
            float in0_val = in0Local.GetValue(i);
            float in1_val = in1Local.GetValue(i);
            float in2_val = in2Local.GetValue(i);
            float in3_val = in3Local.GetValue(i);
            float x_val = in0_val;
            float y_val = in1_val;
            (void)x_val;
            (void)y_val;
            (void)in0_val;
            (void)in1_val;
            (void)in2_val;
            (void)in3_val;
            float out0_val = 0.0f;
            float out1_val = 0.0f;
            float out2_val = 0.0f;
            float out3_val = 0.0f;
            float out4_val = 0.0f;
            float& z_val = out0_val;
            (void)z_val;
            (void)out0_val;
            (void)out1_val;
            (void)out2_val;
            (void)out3_val;
            (void)out4_val;
            { asc::std::quad_fanout(in0_val, in1_val, in2_val, in3_val, out0_val, out1_val, out2_val, out3_val, out4_val); }
            out0Local.SetValue(i, out0_val);
            out1Local.SetValue(i, out1_val);
            out2Local.SetValue(i, out2_val);
            out3Local.SetValue(i, out3_val);
            out4Local.SetValue(i, out4_val);
        }

        outQueue0.EnQue(out0Local);
        outQueue1.EnQue(out1Local);
        outQueue2.EnQue(out2Local);
        outQueue3.EnQue(out3Local);
        outQueue4.EnQue(out4Local);
        inQueue0.FreeTensor(in0Local);
        inQueue1.FreeTensor(in1Local);
        inQueue2.FreeTensor(in2Local);
        inQueue3.FreeTensor(in3Local);

        auto out0Buf = outQueue0.DeQue<float>();
        AscendC::DataCopy(out0Gm[tile * TILE_SIZE], out0Buf, TILE_SIZE);
        outQueue0.FreeTensor(out0Buf);
        auto out1Buf = outQueue1.DeQue<float>();
        AscendC::DataCopy(out1Gm[tile * TILE_SIZE], out1Buf, TILE_SIZE);
        outQueue1.FreeTensor(out1Buf);
        auto out2Buf = outQueue2.DeQue<float>();
        AscendC::DataCopy(out2Gm[tile * TILE_SIZE], out2Buf, TILE_SIZE);
        outQueue2.FreeTensor(out2Buf);
        auto out3Buf = outQueue3.DeQue<float>();
        AscendC::DataCopy(out3Gm[tile * TILE_SIZE], out3Buf, TILE_SIZE);
        outQueue3.FreeTensor(out3Buf);
        auto out4Buf = outQueue4.DeQue<float>();
        AscendC::DataCopy(out4Gm[tile * TILE_SIZE], out4Buf, TILE_SIZE);
        outQueue4.FreeTensor(out4Buf);
    }
}
