# ASC_agent 使用指南

本文档集中说明 ASC_agent 的环境准备、常用工作流、头文件迁移流程、测试迁移流程、
host/kernel 测试逻辑、失败修复闭环、失败分类（环境 vs 代码）、模型取证工具，以及
提示词的单一事实源。

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
`core/testing/operator_kernel_scaffold.py` 中的 `KERNEL_SOC_VERSION`。

运行测试前，ASC_agent 会做若干**环境自愈**（`core/testing/build_env.py`），无需手工干预：

- `cannsim` / `llvm-objdump` 常只在 `source set_env` 后才上 PATH；运行器会在 CANN 安装目录
  探测它们并补进子进程 PATH，避免“装了却找不到”；
- 项目改名/移动后残留的过期 CMake 缓存（`CMAKE_CACHEFILE_DIR` 不匹配）会被自动清理；
- 若 `cannsim` 确实不可用，kernel 测试标记为 **SKIPPED**（不计为失败），host 测试照常进行。

## 2. 常用工作流

> 调用模型的命令默认带 `--show-model-io`：流式实时回显与模型的完整对话（含思考过程
> reasoning_content）。不想刷屏时去掉该参数即可。

只迁移头文件：

```bash
python3 main.py convert --input repos/cccl/libcudacxx/include/cuda/std/__algorithm/transform.h --show-model-io
```

迁移并运行测试：

```bash
python3 main.py convert --input <header> --with-tests --show-model-io
```

迁移、测试、根据失败日志修复并重测：

```bash
python3 main.py convert --input <header> --with-tests --test-feedback-to-model --show-model-io
```

只准备测试文件，不实际运行：

```bash
python3 main.py test --input <header> --prepare-tests-only --show-model-io
```

没有 CANN/cannsim 时只跑 host 测试：

```bash
python3 main.py convert --input <header> --with-tests --host-only --show-model-io
```

使用更小规模的 kernel 快速检查：

```bash
python3 main.py convert --input <header> --with-tests --kernel-fast --show-model-io
```

## 3. 头文件迁移流程

头文件迁移由 `core/migration/pipeline.py` 组织，核心数据流如下：

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

路径映射和 header guard 推导主要由 `core/analysis/path_mapper.py` 负责。典型映射是：

```text
repos/cccl/libcudacxx/include/cuda/std/__algorithm/min.h
  -> repos/accl/asc-stl/include/asc/std/__algorithm/min.h
```

## 4. 测试迁移流程

测试迁移由 `core/testing/test_migrator.py` 负责。它读取：

- CCCL 头文件；
- 已生成的 ACCL 头文件；
- `repos/cccl/libcudacxx/test/libcudacxx/std` 下的 CCCL 测试；
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

如果测试迁移不可用，ASC_agent 会先尝试少数已知形状算子的内置语义 fallback（例如
`generate` / `for_each`）；未知形状只生成 include-only smoke，不猜测 `op(x, y)` 调用。

## 5. Host 测试

host 测试是完整 C++ 文件，写入：

```text
repos/accl/asc-stl/test/asc-stl/asc/host/<algo>_tests.cpp
```

host 测试应该满足：

- include 当前生成的 ACCL 头文件；
- 不依赖 CANN/ACL；
- 逐条打印用例，格式类似 `[host][<algo>] ... got ... expected ...`；
- expected 必须独立计算，不能调用被测的 `asc::std::<algo>` 作为 golden；
- 任一用例失败时进程必须返回非零，不能只打印 `FAIL` 后固定 `return 0`。

## 6. Kernel 测试

kernel 测试生成在：

```text
repos/accl/asc-stl/test/asc-stl/asc/kernel/<algo>_example/
```

生成文件包括：

- `host.h` 和 `host.cpp`：kernel launch glue；
- `kernel.cpp`：AscendC 设备侧逐元素循环；
- `main.cpp`：ACL 初始化、数据拷贝、kernel 启动、回拷和结果校验；
- `CMakeLists.txt`：AscendC 构建入口；
- `run_test.sh`：执行 cmake、make 和 `cannsim record`；
- `kernel_spec.json`：模型填充的算子相关槽位。

职责划分（拆分后的脚手架，单一事实源）：

- `core/testing/operator_kernel_scaffold.py`：AscendC/ACL 的 **C++ 源 + CMake** 生成；
- `core/testing/scaffold_scripts.py`：**shell 运行脚本**生成（kernel `run_test.sh`、host
  `run_host_test.sh`、full_project `run_kernel_full.sh`）；
- `core/testing/scaffold_env.py`：三类脚本**共用的统一环境准备片段**；
- `core/testing/build_env.py`：构建环境探测与自愈（过期缓存、CANN 工具 PATH）；
- `core/testing/operator_test.py`：文件准备、命令执行、日志保存、超时处理、失败分类和通过/失败判定。

host 侧不再依赖签入的 `000_set_env.sh` / `001_setup_build.sh`，而是运行生成的
`run_host_test.sh`（同样源自 `scaffold_scripts` + `scaffold_env`）。旧的 `000`–`004`
脚本已删除。

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
  "element_op_code": "z_val = asc::std::gcd(x_val, y_val);",
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
  "element_op_code": "z_val = asc::std::max(x_val, y_val);",
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

`golden_code` 必须是独立参考实现，禁止调用 `asc::std::*`。

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
- 没有模型 `kernel_spec` 时，已知形状算子可使用内置语义 `kernel_spec`；未知形状回退为
  include/build/launch 冒烟，输出 `KERNEL_SIM_RESULT: SMOKE`（**不计为语义通过**），避免“拿算子和自己比”
  或盲目调用 `op(x, y)` 的自洽假绿/误失败；
- 包装层（`core/testing/operator_test.py`）再校验：返回码为 0、命中 `KERNEL_SIM_RESULT: PASS`、
  且日志不含已知失败特征（CMake 错误、mismatch、ACL 错误、CRLF 污染、command-not-found 等）。

## 9. 测试反馈修复闭环

开启 `--test-feedback-to-model` 后，ASC_agent 会把测试失败信息回传给模型。修复请求包含：

- 当前 ACCL header；
- 当前 host 测试；
- 当前 kernel spec；
- host/kernel 日志（默认经 `agent_tools.distill_error_lines` 蒸馏出 error 行及上下文，
  而非按 12k 字节硬截断——真正的报错常埋在数万行噪音里，硬截断会把它截没）；
- **历轮修复尝试与结果**（`attempt_history`：每轮的根因判定 / 改了哪些件 / 是否通过），
  形成跨轮记忆，避免模型无状态盲改、反复提交被证明无效的修复。

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

修复循环还会**提前止损**，避免空转烧模型调用：

- 失败被判为 **env（环境问题）** 时直接跳过修复循环（见第 10 节）；
- 某轮回传模型的输入与上一轮**完全相同**（无新信息）→ 停止；
- 模型某轮**未返回任何可改动件** → 停止；
- 达到 `retry.max_fix_rounds`（默认 5）→ 停止。

## 10. 失败分类（环境 vs 代码）

`core/testing/failure_triage.py` 在每次失败后给出分类，避免把“改代码无用”的环境问题反复回传模型：

- **env**：构建/工具链/驱动问题——过期 CMakeCache、缺 `llvm-objdump`、缺 `cannsim`、
  驱动符号 `undefined reference to drv*` 等。此类**不进**模型修复循环，直接报“需修环境”。
- **code**：编译错误（`no matching function`、类型不符…）、数值 `Mismatch` 等，模型修复有意义。
- **unknown**：信息不足。

判定时**代码特征优先于环境特征**（真正的编译/数值错总值得回传模型；纯环境失败通常不含这些行）。
能自愈的环境问题（过期缓存、CANN 工具 PATH）由 `core/testing/build_env.py` 在执行前主动修复；缺 `cannsim`
则把 kernel 标为 SKIPPED（不计失败）。

## 11. 模型工具（取证 + 自检，默认开启，覆盖生成+修复全链路）

`config/settings.yaml` 里 `model.tools_enabled` 现默认 `true`（配 `max_tool_rounds`）。工具不再
只接在修复路径，而是由统一工厂 `core/llm/agent_tools.build_toolbox` 注入到三处：头文件初稿生成、
测试迁移、测试反馈修复——让模型在产出结果前就能取证/自检（`core/llm/agent_tools.py`，沙箱限制在
目标仓 / outputs；provider 为 `mock` 时返回 `None` 以保持离线行为）：

| 工具 | 作用 |
|------|------|
| `read_repo_file` | 按需读目标仓任意头（如 `__config`、sibling 算子），不必全塞进 prompt |
| `grep_repo` | 查宏/符号的真实定义（如 `_ASC_AICORE_FN`） |
| `host_syntax_check` | 用 `g++ -fsyntax-only` 先自检 host 产物，省一整轮往返 |
| `extract_error_lines` | 从数万行日志里只抽 error/warning 行回喂 |

工具调用循环在 `model_client.generate_with_tools`（OpenAI 兼容 `tools`，GLM 支持）。生成路径
（初稿 / 测试迁移）以 `core/common/utils.call_model_maybe_tools` 复用同一循环：有工具箱走带工具对话，
否则回退单轮 `generate`。

## 12. 扩展思考

`model.thinking: true`（现为默认）让模型在迁移/修复这类需要分步推理的硬任务上先想后写；流式下
`reasoning_content` 单独实时回显，只把正式 `content` 累积为返回值，故返回仍是干净 JSON
（见 `model_client._generate_stream`）。不需要时把 `thinking` 置 `false` 即可。

## 13. 提示词的单一事实源

`skills/_shared/` 下用三个片段集中表达重复的铁律，各 skill 通过 `{{include: _shared/xxx.md}}`
引用（展开见 `Config.read_skill`），避免多份提示词抄写漂移：

- `operator_contract.md`：算子语义为基准，测试适配算子真实形态；
- `host_test_contract.md`：host 测试逐条打印、expected 独立、失败必返回非零；
- `kernel_spec_contract.md`：kernel_spec 槽位 / IO 1~8 / dtype / golden 独立。

## 14. 示例库扩充（make-example，curation）

few-shot 检索（第 4 节 / `core/knowledge/example_retrieval.py`）只有在示例库够大够普遍时才挑得动。示例是
金标准，因此不手写，而是用 `make-example` 把 `repos/accl` 里**已迁移并通过测试**的算子晋升为示例：

```bash
python3 main.py make-example                    # 列出可晋升候选
python3 main.py make-example clamp sort3 minmax  # 晋升指定算子
python3 main.py make-example --all --overwrite   # 全量刷新
```

实现见 `core/migration/example_promote.py`，把该算子的 CCCL 源头 / ACCL 头 / CCCL 测试 / ACCL host 测试 /
kernel_spec 复制进 `examples/`。要点：

- 这是**人触发的 curation**（把已验证的*输出*沉淀为可复用的*输入*），不破坏运行时 I/O 边界：
  agent 迁移时仍只读 `cccl + examples`、只写 `accl + outputs`。
- **质量门禁**：ACCL 头须含 guard、host 测试须经 `validate_host_test_code`（失败必返回非零）、
  kernel_spec 须经 `validate_kernel_spec`。门禁不过的测试被挡在库外（头若有效仍晋升）。
  实测已拦下 `minmax` 的「假绿」host 测试（只打印 `FAIL` 却始终 `return 0`）。
- 检索生成时默认 `exclude_self`：迁 X 不会拿 X 自己的答案当示例，避免评测泄漏。
