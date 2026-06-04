# ASC_agent

ASC_agent 是一个面向 **CCCL 到 ACCL** 的迁移与验证助手。它以
`libcudacxx` 头文件为输入，生成对应的 `libascendcxx` 头文件，并可以继续迁移
算子测试，在 host 侧和 AscendC kernel 仿真侧验证结果。

当前仓库目录名仍是 `cccl-to-accl-v3`，但项目名称统一为 **ASC_agent**。

## 项目能做什么

1. 读取 `repos/cccl/libcudacxx/include/cuda/std` 下的 CCCL 头文件。
2. 推导 ACCL 目标路径和预期 header guard。
3. 基于提示词与 few-shot 示例调用模型生成 ACCL 头文件。
4. 将生成结果写入 `repos/accl`。
5. 可选：把 CCCL 测试迁移成 ACCL host 测试和 kernel `kernel_spec`。
6. 可选：运行 host C++ 测试和 AscendC kernel 仿真测试。
7. 可选：把测试失败日志回传给模型，修复 header、host 测试或 kernel spec。

## 快速命令

```bash
# 离线自检，不需要 API key 或 CANN。
python3 main.py selftest

# 迁移一个 CCCL 头文件并写入 ACCL 目标仓。
python3 main.py convert --input repos/cccl/libcudacxx/include/cuda/std/__algorithm/min.h

# 迁移并运行 host/kernel 测试。
python3 main.py convert --input <header> --with-tests

# 迁移、测试，并根据失败日志自动修复。
python3 main.py convert --input <header> --with-tests --test-feedback-to-model

# 对已经迁移好的目标生成/运行测试。
python3 main.py test --input <header>
```

没有 CANN/cannsim 的机器可以加 `--host-only`。需要更快的 kernel 小规模检查时可以加
`--kernel-fast`。

## 项目分层架构（分层 / 分模块）

按职责自顶向下分为 5 层，上层只依赖下层，依赖注入让每层都能被 mock 替换、离线测试：

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ L1 入口层 (CLI)                                                                │
│   main.py  ——  convert / run / batch / test / selftest 子命令、参数解析、退出码 │
└───────────────────────────────┬───────────────────────────────────────────────┘
                                │ 调用
┌───────────────────────────────▼───────────────────────────────────────────────┐
│ L2 编排层 (Orchestration)                                                       │
│   pipeline.py            头文件迁移主流程：初稿 → 提交基线 → 多轮修复 → push       │
│   main._run_convert_test_loop   测试闭环：迁移测试 → 跑测 → 失败回传模型 → 重测     │
└───────────────────────────────┬───────────────────────────────────────────────┘
                                │ 编排以下能力
┌───────────────────────────────▼───────────────────────────────────────────────┐
│ L3 核心能力层 (Core capabilities) —— 三个模块组                                   │
│                                                                                │
│   ① 迁移 / 生成        ② 测试 / 验证                 ③ 提交校验                   │
│   pipeline._rewrite    operator_test.py            repo_verify.py             │
│   test_migrator.py     operator_kernel_scaffold.py                            │
│   fix_once.py          (host 编译运行 + kernel cannsim 仿真 + 通过判定)          │
└───────────────────────────────┬───────────────────────────────────────────────┘
                                │ 依赖
┌───────────────────────────────▼───────────────────────────────────────────────┐
│ L4 基础设施层 (Infrastructure)                                                  │
│   config.py        配置加载 / ${ENV} 展开 / 路径解析                             │
│   path_mapper.py   CCCL 路径 → ACCL 路径 / header guard 推导                     │
│   model_client.py  LLM 客户端(Zhipu/Mock) + JSON 解析 + 文本归一化               │
│   utils.py         模型 IO、读写文件等通用工具                                    │
└───────────────────────────────┬───────────────────────────────────────────────┘
                                │ 读取 / 写入
┌───────────────────────────────▼───────────────────────────────────────────────┐
│ L5 资源 / 数据层 (Resources & Data)                                             │
│   skills/        模型提示词        examples/   few-shot 示例(头/测试)             │
│   config/*.yaml  设置 / 批量清单    repos/cccl 源仓 · repos/accl 目标仓+生成产物   │
│   outputs/       模型 IO、生成产物、host/kernel 测试日志                          │
└───────────────────────────────────────────────────────────────────────────────┘
```

| 层 | 职责 | 关键模块 | 可替换/离线 |
|----|------|----------|------------|
| L1 入口 | 命令分发、参数、退出码 | `main.py` | `selftest` 离线冒烟 |
| L2 编排 | 串联生成→提交→测试→修复闭环 | `pipeline.py` | 注入 Mock/Fake 依赖 |
| L3 能力 | 迁移生成 / host·kernel 测试 / 提交校验 | `test_migrator` · `operator_test` · `operator_kernel_scaffold` · `fix_once` · `repo_verify` | `--mock` / `--test-dry-run` |
| L4 基础 | 配置、路径映射、模型客户端 | `config` · `path_mapper` · `model_client` · `utils` | `MockModelClient` |
| L5 资源 | 提示词、示例、仓库、产物 | `skills/` · `examples/` · `repos/` · `outputs/` | 全部在仓内，无需外部依赖 |

## 项目层次结构图

```text
ASC_agent
├── main.py                         命令行入口：convert / run / batch / test / selftest
├── config/
│   ├── settings.yaml               路径、模型、重试和测试配置
│   └── batch_manifest.yaml         批量迁移清单
├── core/
│   ├── config.py                   配置加载与路径解析
│   ├── path_mapper.py              CCCL 路径到 ACCL 路径/header guard 的映射
│   ├── model_client.py             模型客户端、JSON 解析与文本归一化
│   ├── pipeline.py                 头文件迁移主流程
│   ├── test_migrator.py            CCCL 测试到 ACCL host/kernel spec 的迁移
│   ├── operator_test.py            host/kernel 测试准备、执行和判定
│   ├── operator_kernel_scaffold.py AscendC/ACL kernel 测试脚手架生成
│   ├── fix_once.py                 基于提交日志或测试日志的单轮修复
│   └── repo_verify.py              仓库格式化/提交类校验
├── skills/                         模型提示词
├── examples/
│   ├── headers/                    头文件迁移 few-shot 示例
│   └── tests/                      测试迁移 few-shot 示例
├── repos/
│   ├── cccl/                       CCCL 源侧样例仓
│   └── accl/                       ACCL 目标仓、生成头文件和生成测试
├── docs/
│   └── guide.md                    中文使用指南与测试逻辑说明
├── tests/                          离线 pytest 单测
└── outputs/                        模型输入输出、生成产物和测试日志
```

## 数据流图

```text
CCCL 头文件
  │
  ├─ path_mapper.py
  │    └─ 推导 ACCL target_relpath 与 expected_header_guard
  │
  ├─ pipeline.py
  │    ├─ 读取 examples/headers 与 skills/rewrite_initial.md
  │    ├─ 调用模型生成 ACCL header
  │    └─ 写入 repos/accl/libascendcxx/include/ascend/std/...
  │
  ├─ test_migrator.py（可选）
  │    ├─ 读取 CCCL 测试、ACCL header、examples/tests
  │    ├─ 调用模型生成 host_test_code
  │    └─ 调用模型生成 kernel_spec
  │
  ├─ operator_test.py（可选）
  │    ├─ 写入 host 测试：
  │    │    repos/accl/libascendcxx/test/libascendcxx/ascend/host/<algo>_tests.cpp
  │    ├─ 生成 kernel 测试目录：
  │    │    repos/accl/libascendcxx/test/libascendcxx/ascend/kernel/<algo>_example/
  │    ├─ 运行 host C++ 测试
  │    └─ 运行 AscendC/cannsim kernel 仿真
  │
  └─ fix_once.py（可选）
       ├─ 收集 host/kernel 日志与当前 header/test/spec
       ├─ 调用模型返回 header_code / host_test_code / kernel_spec 的任意子集
       └─ 写回后再次进入 operator_test.py 重测
```

## 测试模型

host 测试是每个算子独立生成的完整 C++ 文件。kernel 测试由固定 AscendC/ACL/cannsim
脚手架加模型填充的 `kernel_spec` 组成：

```json
{
  "gm_inputs": 2,
  "gm_outputs": 1,
  "dtype": "float",
  "input_init": "h_in0[i] = ...;",
  "element_op_code": "out0_val = ...;",
  "golden_code": "expected0 = ...;"
}
```

kernel 脚手架支持 1 到 8 个 GM 输入、1 到 8 个 GM 输出。旧的单输出别名仍然可用：
`x_val`、`y_val`、`z_val`、`x_ref`、`y_ref` 和 `expected`。

`dtype`（可选，默认 `float`）决定整条标量流水线的类型：浮点用 `float` / `double`（容差比对），
整数算子（`gcd` / `lcm`）用 `int32_t` / `int64_t`（精确相等比对）。

`golden_code` 必须是**独立**参考实现（禁止调用被测的 `ascend::std::*`）；kernel 的通过判定
以仿真日志 `cannsim.log` 里真实的逐元素 golden 校验为准（命中 `verification passed.`
且无 `Mismatch`），而非 cannsim 录制是否成功。没有 `kernel_spec` 时只做 build+launch
冒烟（输出 `SMOKE`，不计为语义通过）。

更完整的安装、工作流和测试逻辑见 [docs/guide.md](docs/guide.md)。
