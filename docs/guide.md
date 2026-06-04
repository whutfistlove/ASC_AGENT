# ASC_agent 使用指南

本文档集中说明 ASC_agent 的环境准备、常用工作流、头文件迁移流程、测试迁移流程、
host/kernel 测试逻辑以及失败修复闭环。

## 1. 环境准备

安装基础工具：

```bash
sudo apt update
sudo apt install -y build-essential cmake git python3 python3-pip dos2unix
pip install -r requirements.txt
```

配置模型密钥：

```bash
cp .env.example .env
# 编辑 .env，设置 ZHIPU_API_KEY=<key>
```

kernel 仿真需要安装带 `cannsim` 的 CANN 环境。当前项目生成 kernel CMake 文件时默认使用：

```text
SOC_VERSION = Ascend950PR_9599
cannsim -s Ascend950
```

如果本机 CANN 支持的 SOC 名称不同，需要调整
`core/operator_kernel_scaffold.py` 中的 `KERNEL_SOC_VERSION`。

## 2. 常用工作流

只迁移头文件：

```bash
python3 main.py convert --input repos/cccl/libcudacxx/include/cuda/std/__algorithm/min.h
```

迁移并运行测试：

```bash
python3 main.py convert --input <header> --with-tests
```

迁移、测试、根据失败日志修复并重测：

```bash
python3 main.py convert --input <header> --with-tests --test-feedback-to-model
```

只准备测试文件，不实际运行：

```bash
python3 main.py test --input <header> --prepare-tests-only
```

没有 CANN/cannsim 时只跑 host 测试：

```bash
python3 main.py convert --input <header> --with-tests --host-only
```

使用更小规模的 kernel 快速检查：

```bash
python3 main.py convert --input <header> --with-tests --kernel-fast
```

## 3. 头文件迁移流程

头文件迁移由 `core/pipeline.py` 组织，核心数据流如下：

```text
CCCL header
  -> path_mapper 推导 ACCL 目标路径和 header guard
  -> 读取 examples/headers/* 作为 few-shot 示例
  -> 读取 skills/rewrite_initial.md 作为迁移提示词
  -> 调用模型生成 ACCL header
  -> 归一化生成文本
  -> 写入 repos/accl
```

头文件迁移示例位于：

```text
examples/headers/max.cccl.h
examples/headers/max.accl.h
examples/headers/os.cccl.h
examples/headers/os.accl.h
```

路径映射和 header guard 推导主要由 `core/path_mapper.py` 负责。典型映射是：

```text
repos/cccl/libcudacxx/include/cuda/std/__algorithm/min.h
  -> repos/accl/libascendcxx/include/ascend/std/__algorithm/min.h
```

## 4. 测试迁移流程

测试迁移由 `core/test_migrator.py` 负责。它读取：

- CCCL 头文件；
- 已生成的 ACCL 头文件；
- `repos/cccl/libcudacxx/test/std` 下的 CCCL 测试；
- `examples/tests` 下的测试迁移 few-shot 示例。

模型需要返回：

```json
{
  "host_test_code": "<完整的 ACCL host 测试>",
  "kernel_spec": {
    "gm_inputs": 2,
    "gm_outputs": 1,
    "input_init": "...",
    "element_op_code": "...",
    "golden_code": "..."
  },
  "notes": "..."
}
```

如果测试迁移不可用，ASC_agent 会退回到旧的 smoke-test 模板，以保证离线和 mock 流程仍然可用。

## 5. Host 测试

host 测试是完整 C++ 文件，写入：

```text
repos/accl/libascendcxx/test/libascendcxx/ascend/host/<algo>_tests.cpp
```

host 测试应该满足：

- include 当前生成的 ACCL 头文件；
- 不依赖 CANN/ACL；
- 逐条打印用例，格式类似 `[host][<algo>] ... got ... expected ...`；
- expected 必须独立计算，不能调用被测的 `ascend::std::<algo>` 作为 golden；
- 任一用例失败时进程必须返回非零，不能只打印 `FAIL` 后固定 `return 0`。

## 6. Kernel 测试

kernel 测试生成在：

```text
repos/accl/libascendcxx/test/libascendcxx/ascend/kernel/<algo>_example/
```

生成文件包括：

- `host.h` 和 `host.cpp`：kernel launch glue；
- `kernel.cpp`：AscendC 设备侧逐元素循环；
- `main.cpp`：ACL 初始化、数据拷贝、kernel 启动、回拷和结果校验；
- `CMakeLists.txt`：AscendC 构建入口；
- `run_test.sh`：执行 cmake、make 和 `cannsim record`；
- `kernel_spec.json`：模型填充的算子相关槽位。

其中，`core/operator_kernel_scaffold.py` 负责生成 AscendC/ACL kernel 脚手架；
`core/operator_test.py` 负责文件准备、命令执行、日志保存、超时处理和通过/失败判定。

## 7. Kernel Spec 契约

kernel 脚手架支持 1 到 8 个 GM 输入和 1 到 8 个 GM 输出。

可选字段 `dtype` 决定整条标量流水线的类型（默认 `float`）：

- 浮点算子用 `float` / `double`，按容差 `1e-5` 比对；
- 整数语义算子（如 `gcd` / `lcm`）必须用 `int32_t` / `int64_t`，脚手架改用**精确相等**比对
  （否则用 float 测整数算子语义是错的）；
- 支持集合：`float` / `double` / `int32_t` / `int64_t` / `int16_t`，未知类型回退 `float`。

```json
{ "gm_inputs": 2, "gm_outputs": 1, "dtype": "int64_t",
  "input_init": "h_x[i] = static_cast<int64_t>(i % 50); h_y[i] = static_cast<int64_t>((i * 7) % 50);",
  "element_op_code": "z_val = ascend::std::gcd(x_val, y_val);",
  "golden_code": "int64_t a=x_ref,b=y_ref; while(b){int64_t t=b;b=a%b;a=t;} expected = a<0?-a:a;" }
```

`input_init` 可用变量：

```text
h_in0[i] ... h_inN[i]
h_x == h_in0
h_y == h_in1，当 gm_inputs >= 2；否则是 dummy vector
```

`element_op_code` 可用变量：

```text
in0_val ... inN_val
out0_val ... outM_val
x_val == in0_val
y_val == in1_val，当 gm_inputs >= 2；否则为 0
z_val == out0_val
```

`golden_code` 可用变量：

```text
in0_ref ... inN_ref
expected0 ... expectedM
x_ref == in0_ref
y_ref == in1_ref，当 gm_inputs >= 2；否则为 0
expected == expected0
```

二输入单输出示例：

```json
{
  "gm_inputs": 2,
  "gm_outputs": 1,
  "input_init": "h_x[i] = static_cast<float>(i); h_y[i] = static_cast<float>(i * 2);",
  "element_op_code": "z_val = ascend::std::max(x_val, y_val);",
  "golden_code": "expected = (x_ref < y_ref) ? y_ref : x_ref;"
}
```

四输入五输出示例：

```json
{
  "gm_inputs": 4,
  "gm_outputs": 5,
  "input_init": "h_in0[i]=...; h_in1[i]=...; h_in2[i]=...; h_in3[i]=...;",
  "element_op_code": "out0_val=...; out1_val=...; out2_val=...; out3_val=...; out4_val=...;",
  "golden_code": "expected0=...; expected1=...; expected2=...; expected3=...; expected4=...;"
}
```

`golden_code` 必须是独立参考实现，禁止调用 `ascend::std::*`。

## 8. 日志与通过标准

host 测试日志：

```text
outputs/host_test_<algo>.log
```

kernel 包装层日志：

```text
outputs/kernel_test_<algo>.log
```

`main.cpp` 中用户程序的实际 stdout 经常会被 cannsim 重定向到生成的仿真目录，例如：

```text
repos/accl/.../<algo>_example/build/cannsim_*/cannsim.log
```

kernel 通过标准比“命令返回码为 0”更严格，且**以被测程序真实的数值校验为准**，
而不是 cannsim 录制是否成功（否则数值算错会被掩盖成假绿）：

- `run_test.sh` 在 cannsim 结束后，定位 `build/cannsim_*/cannsim.log`（被测程序真实 stdout），
  只有当其中**不含 `Mismatch at`** 且**命中独立 golden 的 `kernel simulation verification passed.`**
  时，才输出 `KERNEL_SIM_RESULT: PASS`；
- 数值 mismatch / 找不到 cannsim.log → 直接判失败（非零退出）；
- 没有 `kernel_spec` 的回退档只做 build+launch 冒烟，输出 `KERNEL_SIM_RESULT: SMOKE`
  （**不计为语义通过**），避免“拿算子和自己比”的自洽假绿；
- 包装层（`operator_test.py`）再校验：返回码为 0、命中 `KERNEL_SIM_RESULT: PASS`、
  且日志不含已知失败特征（CMake 错误、mismatch、ACL 错误、CRLF 污染、command-not-found 等）。

## 9. 测试反馈修复闭环

开启 `--test-feedback-to-model` 后，ASC_agent 会把测试失败信息回传给模型。修复请求包含：

- 当前 ACCL header；
- 当前 host 测试；
- 当前 kernel spec；
- host/kernel 日志。

模型可以返回以下任意子集：

- `header_code`；
- `host_test_code`；
- `kernel_spec`。

算子语义始终是基准。如果失败根因是测试写错，就修测试；不能为了迁就错误测试而改变算子的签名、
返回类型或语义。

为了避免错误修复污染下一轮，当前测试修复入口还会做以下校验：

- 模型输出必须是严格 JSON 对象，不能带 Markdown 或额外分析文本；
- `host_test_code: null` 表示不修改 host 测试，不会被写成源码文本；
- 新的 host 测试必须保证失败时返回非零。
