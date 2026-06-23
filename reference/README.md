# reference/ —— CUDA→Ascend 迁移知识库（自官方 `cuda2ascend-simt` 照搬）

本目录整体来自官方 Skill 项目 **`cuda2ascend-simt`**（华为 CANN，迁移层为
runtime/device/kernel：`.cu→.asc`、`cudaMalloc→aclrtMalloc`、torch 扩展）。
照搬日期：2026-06-15。作为本项目（CCCL→ASC-STL **头文件层**）的可审计知识库与方法论参考。
照搬后做了三处归位：① 新增本层的 `symbol_mapping.yaml`（管线实际注入的表）；② 删除跨层的
`example/`；③ 把官方 `SKILL.md` 移至 `skills/cuda2ascend-simt.SKILL.md`（与项目自有 skills 同处）。

## 知识库分层

`reference/` 里现在混合了两类材料：

1. **本项目 ASC-STL 头文件层会直接用的知识**：路径/命名/宏映射、迁移策略、少量语法与约束触发规则。
2. **官方 cuda2ascend-simt 的跨层资料**：CUDA runtime/device API、torch/pybind/sample 工作流模板、硬件验收模板等。

为了避免把不同层级混进同一个 prompt，按下面的接入等级维护：

| 等级 | 含义 | 处理方式 |
|------|------|----------|
| A. 运行时事实源 | 本项目当前迁移行为直接依赖 | `Config.load()` 或 `KnowledgeBase.load()` 读取，必须保持可审计 |
| B. 触发式注入 | 对 header/test 迁移可能有用，但只在源码命中特征时注入 | 通过 `core/knowledge_base.py` 白名单触发，避免噪声 |
| C. 方法论/Schema | 不进入 prompt，约束知识库维护格式或验证口径 | 人看、测试/工具未来可用 |
| D. 条件候选 | 当前不自动接入，但某些 header 落到设备 intrinsic 时可能需要 | 后续做按需检索，不默认注入 |
| E. 跨层归档 | 与 ASC-STL 头文件迁移不同层，当前基本无关 | 保留作官方资料来源，不进当前迁移链路 |

## 文件清单

| 路径 | 等级 | 是什么 | 当前是否被本项目读取 | 与本项目关系 |
|------|------|--------|----------------------|--------------|
| `symbol_mapping.yaml` | A | **本项目自建**的 header 层符号/宏/命名空间/include/header guard 映射；同时承载 `segment_substitutions`、`migration_policy` 与 `symbol_dependencies` | 是。`Config.load()` 读取迁移策略和符号隐含依赖；`KnowledgeBase.load()` 读取符号映射并注入 prompt | **核心相关**，这是 ASC-STL 头文件迁移的事实源 |
| `grammar_rules.yaml` | B | CUDA/SIMT 语法改写规则，如 `__device__`、`__shared__`、`assert`、`printf` | 是。`KnowledgeBase.load()` 读取，源码命中触发词时注入 | **部分相关**。普通 libcudacxx header 很少直接出现 CUDA kernel 语法，但测试迁移、kernel scaffold、设备 helper 可能用到 |
| `constraint_rules.yaml` | B | 不支持/受限特性规则，如 texture、cooperative groups、nvrtc、device double、device-side `std::`、struct by value | 是。`KnowledgeBase.load()` 读取，命中高信号关键词时注入 | **部分相关**。其中 `double`、device-side `std::`、struct-by-value 对 kernel 测试/设备路径有参考价值；torch/JIT/OpenGL 类规则当前弱相关 |
| `grammar.md` | C | `grammar_rules.yaml` 的人工浏览说明/来源文本 | 否 | **间接相关**，用于维护 YAML，不应直接塞给模型 |
| `constraints.md` | C | `constraint_rules.yaml` 的人工浏览说明/来源文本 | 否 | **间接相关**，用于维护 YAML，不应直接塞给模型 |
| `rule_schema.md` | C | grammar/constraint 规则字段 schema | 否 | **维护相关**，后续可加 CI 校验 YAML 字段 |
| `schema.md` | C | `api-mapping/*.yaml` 的字段 schema | 否 | **维护相关**，主要约束 api-mapping，不直接参与 header 迁移 |
| `validation-checklist.md` | C/E | 官方 sample/torch_npu/pybind 迁移的“可报告成功”硬门禁 | 否 | **方法论相关，但当前不直接适配**。本项目已用 semantic/smoke 区分替代其中一部分验收思想 |
| `api-mapping/device_api.yaml` | D | CUDA device API / intrinsic 到 Ascend 的映射，如 math、type-conversion、comparison、warp、atomic | 否 | **条件相关**。ASC-STL 算法/numeric 头如果生成设备代码并碰到 intrinsic，可按需检索；当前不默认注入 |
| `api-mapping/device_api.md` | D/C | `device_api.yaml` 的人工浏览视图 | 否 | **条件相关**，维护 YAML 时参考 |
| `api-mapping/runtime_api.yaml` | E | CUDA Runtime API 到 Ascend ACL 映射，如 `cudaMalloc`、stream、event、device 管理 | 否 | **当前基本无关**。ASC-STL 头文件迁移不处理 CUDA runtime 调用；除非以后扩展到 runtime wrapper 迁移 |
| `api-mapping/runtime_api.md` | E/C | `runtime_api.yaml` 的人工浏览视图 | 否 | **当前基本无关**，维护 runtime API 映射时参考 |
| `assets/plan-template-zh.md` | E | 官方迁移计划中文模板 | 否 | **当前无直接关系**。本项目不按官方 sample/torch 交付文档流运行 |
| `assets/readme-template-zh.md` | E | 官方交付 README 中文模板 | 否 | **当前无直接关系** |
| `assets/approval-message-template-zh.md` | E | 官方审批消息模板 | 否 | **当前无直接关系** |
| `README.md` | C | 本目录说明与接入边界 | 人读 | **维护相关** |

> 注 1：官方 `SKILL.md`（迁移 workflow 全文 / 方法论 playbook）已移至 `skills/cuda2ascend-simt.SKILL.md`，与项目自有 skills 同处。它是**方法论参考**，非 `read_skill()` 加载的提示词。
> 注 2：官方原本的 `reference/example/`（runtime/kernel/torch 层 cuda↔simt 工程）已删除——它与本项目 header 层 `examples/`（few-shot 库）不同级、用不上，避免"example"概念混淆。

## 与本项目无关或弱相关的部分

严格按当前目标“CCCL/libcudacxx header → ASC-STL header”来看：

- **当前基本无关**：`api-mapping/runtime_api.*`。它解决 CUDA Runtime/ACL 迁移，而本项目迁的是 C++ 标准库头文件，不迁 `cudaMalloc`、stream、event。
- **当前无直接关系**：`assets/*-zh.md`。它们是官方交付文档模板，本项目没有使用这套交付物生成流程。
- **弱相关/方法论相关**：`validation-checklist.md`。它面向 sample/torch_npu/pybind 的硬件验收；本项目只吸收“不能把 smoke 当成功”这类思想，具体字段不直接套用。
- **部分规则弱相关**：`constraint_rules.yaml` 中 torch/JIT/OpenGL/runtime compilation 等规则。它们保留是为了来源完整，但当前 header 迁移很少触发。
- **条件相关**：`api-mapping/device_api.*`。它不是当前 header 路径策略，但如果迁移某些 numeric/algorithm 头时需要替换设备 intrinsic，这部分会成为按需查询库。

## 维护约定（沿用官方）

- **YAML 是 source of truth，`.md` 只是浏览视图**；先改 YAML 再同步 MD。
- 每条记录保留 provenance：`source:[...]`、`reviewed_by: human|agent`、`reviewed_at: ISO date`。
- 不要把未确认的映射从 `unknown` 直接改成 `mapped`——至少补一个 `source` 和复核日期。
- 按需加载：用某条规则/某类映射时只读对应文件，不要整库塞进上下文。

## 已接入（本库如何被调用）

- **加载**：`core/knowledge_base.py` 的 `KnowledgeBase.load(reference_dir)` 读
  `symbol_mapping.yaml` / `grammar_rules.yaml` / `constraint_rules.yaml`；缺文件自动降级为空（不崩）。
- **路径**：`config/settings.yaml` 的 `paths.reference_dir`（默认 `${PROJECT_ROOT}/reference`），
  访问器 `Config.reference_dir`。
- **策略加载**：`Config.load()` 会读取 `symbol_mapping.yaml`，把
  `segment_substitutions`、`migration_policy` 与 `symbol_dependencies` 覆盖进运行时 config；
  `settings.yaml` 不再维护这三类策略。
- **符号依赖分析**：`core/inventory.py` 会用 `symbol_dependencies` 在去除注释/字符串后的源码中匹配
  `_CUDA_VSTD::move` 等符号，`core/dep_graph.py` 会把命中的提供头加入依赖边，解决“源码用了符号但没有
  显式 include”的闭包缺漏。
- **注入**：改写（`core/pipeline.py` `_rewrite`）与测试迁移（`core/test_migrator.py`
  `migrate_operator_tests`）在调模型前，按当前头涉及的符号 `render_block()` 出命中项，
  拼进提示词。always_inject 的符号映射对每个头都注入；语法/约束规则按**白名单触发词**
  （`double`/`complex`/`__device__`/`assert` 等）命中才注入，避免噪声。
- **验证**：`tests/test_knowledge_base.py` 离线单测覆盖加载/注入/触发/缺库降级；
  `tests/test_config.py` 覆盖 reference 策略覆盖 config 的行为，`tests/test_inventory.py` /
  `tests/test_dep_graph.py` 覆盖符号依赖扫描与依赖边生成。

## 待办（进一步收敛）

- 减少 `core/config.py` 中仅供无 reference 测试项目使用的 fallback 常量，或把 fallback 测试夹具也显式带上最小 reference。
- 把官方 `api-mapping/` 的 `device/math`·`type-conversion`·`comparison` 子集接入 `knowledge_base`，
  当算法落到设备 intrinsic 时按需检索（体量大，仍不默认注入）。
