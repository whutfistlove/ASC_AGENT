# cccl-to-accl-v3

调用大模型把 **CCCL**（libcudacxx）头文件自动改写为 **ACCL**（libascendcxx）目标文件，并在项目内执行 **host / kernel 仿真测试**验证结果（kernel 侧用昇腾 `cannsim` camodel 真机模拟）。

环境配置与运行命令见 [docs/wsl_guide.md](docs/wsl_guide.md)。

---

## 架构总览

```text
                          ┌──────────────────────────────────────────────┐
                          │                  main.py (CLI)                │
                          │   convert · run · batch · test · selftest     │
                          └───────────────────────┬──────────────────────┘
                                                  │
                 ┌────────────────────────────────▼─────────────────────────────────┐
                 │                        core/pipeline.py                           │
                 │                      （主编排 / 修复闭环）                          │
                 └─┬───────────┬───────────┬───────────┬───────────┬────────────┬────┘
                   │           │           │           │           │            │
        ┌──────────▼──┐ ┌──────▼─────┐ ┌───▼──────┐ ┌──▼─────────┐ ┌▼──────────┐ ┌▼─────────┐
        │  config.py  │ │path_mapper │ │model_    │ │repo_       │ │operator_  │ │fix_once  │
        │ 分层配置 +  │ │ 路径/guard │ │client.py │ │verify.py   │ │test.py    │ │ 单轮修复 │
        │ 环境变量展开│ │   推导     │ │Zhipu/Mock│ │git 提交检查 │ │host/kernel│ │（失败回灌│
        │             │ │            │ │ + skills │ │license/style│ │测试生成执行│ │  模型）  │
        └─────────────┘ └────────────┘ └────┬─────┘ └────────────┘ └─────┬─────┘ └────┬─────┘
                                            │                            │            │
                                      skills/*.md                        │            │
                                      （提示词）                          │            │
                                                                         │            │
   数据流：                                                              │            │
   ┌────────────┐  map  ┌──────────────┐ rewrite ┌──────────────┐ write ┌───────────▼─────┐
   │ CCCL 头文件 │ ────▶ │ target 路径/  │ ──────▶ │ 模型生成 +   │ ────▶ │ repos/accl/...  │
   │ repos/cccl │       │ header guard │         │ normalize 归一│       │ (ACCL 目标文件) │
   └────────────┘       └──────────────┘         └──────────────┘       └──────┬──────────┘
                                                                                │
                          ┌─────────────────────────────────────────────────────┘
                          │                  operator_test.py
                          ▼
        ┌─────────────────────────────────┐        ┌────────────────────────────────────────┐
        │  host 测试                       │        │  kernel 测试 (run_test 模式)             │
        │  source 000_set_env.sh           │        │  source CANN set_env.sh                  │
        │  → make <algo>_host_test         │        │  → cmake + make (AscendC 编译)           │
        │  → ctest -R host.<algo>          │        │  → cannsim record -s Ascend950 (camodel) │
        │  （编译期 + 运行期断言）          │        │  → main.cpp 逐元素数值校验               │
        └─────────────────────────────────┘        └────────────────────────────────────────┘
                          │                                          │
                          └──────────────► 通过/失败 ◄───────────────┘
                                   失败 → fix_once 回灌模型 → 重测（最多 N 轮）
```

迁移一个算子的端到端流程：**读取 CCCL 头文件 → 路径/guard 推导 → 模型改写（带 skills 提示词与示例对）→ 输出归一化 → 写入 ACCL 目标文件 →（可选）git 提交检查 →（可选）host/kernel 测试 → 失败则回灌模型修复并重测**。

---

## 目录结构

```text
cccl-to-accl-v3/
├── main.py                  # 入口：convert / run / batch / test / selftest
├── requirements.txt
├── .env.example             # 复制为 .env，填入 ZHIPU_API_KEY
├── config/
│   ├── settings.yaml        # 用户配置（覆盖默认值）
│   └── batch_manifest.yaml  # 批量转换清单
├── core/
│   ├── config.py            # 分层配置 + 环境变量展开
│   ├── path_mapper.py       # 路径/guard 推导
│   ├── model_client.py      # Zhipu REST + Mock
│   ├── repo_verify.py       # git 提交检查（可 dry-run）
│   ├── operator_test.py     # host/kernel 测试生成与执行（含 fast 档、超时、PASS 标记判定）
│   ├── fix_once.py          # 单轮修复
│   ├── pipeline.py          # 主编排逻辑
│   └── utils.py
├── repos/
│   ├── cccl/                # 源仓库（libcudacxx 头文件）
│   └── accl/                # 目标仓库（libascendcxx + host/kernel 测试）
├── skills/                  # 模型提示词
├── examples/                # 成功示例对（CCCL → ACCL）
├── tests/                   # pytest 离线测试（56 项）
├── docs/
│   └── wsl_guide.md         # WSL 环境配置与运行指南
└── outputs/                 # 运行产物（日志、结果、模型交互记录）
```

---

## 快速开始

```bash
# 1. 离线自检（不需要 API Key / 网络 / CANN）
python3 main.py selftest

# 2. 仅转换（不测试、不提交）
python3 main.py convert --input repos/cccl/libcudacxx/include/cuda/std/__algorithm/min.h

# 3. 转换 + host/kernel 测试（需 CANN + cannsim）
python3 main.py convert --input <header> --with-tests

# 4. 转换 + 测试，失败自动回灌模型修复重测
python3 main.py convert --input <header> --with-tests --test-feedback-to-model
```

详细的三种运行模式与环境准备见 [docs/wsl_guide.md](docs/wsl_guide.md)。

---

## 测试链路（host / kernel）

`core/operator_test.py` 自动为每个算子生成并运行两侧测试（源自 mylearn 的双侧测试逻辑，已整合进本项目）：

- **host 测试**：`ctest -R host.<algo>`，编译期 + 运行期断言，快速可靠。
- **kernel 测试**：`run_test.sh` → cmake/make 用 AscendC 编译 kernel → `cannsim record -s Ascend950` 在 `Ascend950PR_9599` camodel 上仿真 → `main.cpp` 逐元素数值校验。

判定通过**不只看退出码**：必须命中 `KERNEL_SIM_RESULT: PASS` 标记且日志无失败特征（避免 `set -e` 被 CRLF 破坏后假阳性）。脚本写盘强制 LF，执行前再规整一次。

### 快速档 vs 完整档

camodel 是 cycle-accurate 的，完整 workload（8 核 × 32 tile × 64 = 16384 元素）单次仿真约 **9 分钟**。提供 `--kernel-fast` 快速档（1 核 × 1 tile = 64 元素）：实测仿真本身从 ~9 分钟降到**近乎瞬时**，整轮（含 AscendC 重新编译）约 **2 分钟**，适合 CI/冒烟：

```bash
# 快速档（默认关闭）；最终验证去掉该 flag 用完整档
python3 main.py convert --input <header> --with-tests --kernel-fast

# 调整 kernel 超时（默认 1200s）
python3 main.py convert --input <header> --with-tests --kernel-timeout 1800
```

> fast/full 切换会按文件顶部的 `auto-workload=<tag>` 标记自动重生成 `kernel.cpp` / `main.cpp`，同档位则保留你的手改。

---

## 配置说明

所有配置项在 `core/config.py` 的 `DEFAULTS` 里有默认值，`config/settings.yaml` 只写需要覆盖的字段。字符串支持 `${ENV}` 和 `${ENV:-默认值}` 展开，内置 `PROJECT_ROOT` 和 `HOME`。

常用字段：

| 字段 | 说明 | 默认值 |
|------|------|--------|
| `paths.cccl_repo` | 源仓库路径 | `repos/cccl` |
| `paths.accl_repo` | 目标仓库路径 | `repos/accl` |
| `model.model_name` | 模型名称 | `glm-5` |
| `model.stream` | 流式输出 | `true` |
| `model.thinking` | 开启 thinking | `false` |
| `retry.max_fix_rounds` | 最大修复轮数 | `5` |
| `tests.kernel_timeout_sec` | kernel 测试超时（秒） | `1200` |
| `tests.host_timeout_sec` | host 测试超时（秒） | `600` |
| `tests.fast_kernel` | 默认启用 kernel 快速档 | `false` |

API Key 放 `.env`（不提交 git）：

```bash
cp .env.example .env
# 编辑 .env 填入 ZHIPU_API_KEY=<key>
```
