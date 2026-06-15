# reference/ —— CUDA→Ascend 迁移知识库（自官方 `cuda2ascend-simt` 照搬）

本目录整体来自官方 Skill 项目 **`cuda2ascend-simt`**（华为 CANN，迁移层为
runtime/device/kernel：`.cu→.asc`、`cudaMalloc→aclrtMalloc`、torch 扩展）。
照搬日期：2026-06-15。作为本项目（CCCL→ASC-STL **头文件层**）的可审计知识库与方法论参考。
照搬后做了三处归位：① 新增本层的 `symbol_mapping.yaml`（管线实际注入的表）；② 删除跨层的
`example/`；③ 把官方 `SKILL.md` 移至 `skills/cuda2ascend-simt.SKILL.md`（与项目自有 skills 同处）。

## 目录内容

| 路径 | 是什么 |
|------|--------|
| `api-mapping/device_api.{yaml,md}` | **945** 条 CUDA device API → Ascend 映射（math 426 / type-conversion 265 / comparison 105 / vector-type 60 / warp 20 / atomic 20 / …） |
| `api-mapping/runtime_api.{yaml,md}` | **230** 条 CUDA runtime API → Ascend ACL 映射（device/stream/memory/event/… 管理） |
| `grammar.md` + `grammar_rules.yaml` | 语法改写规则（`__device__→__aicore__`、`__shared__→__ubuf__`、assert/printf 头等） |
| `constraints.md` + `constraint_rules.yaml` | 不支持/受限特性（cooperative groups、texture、nvrtc、device double、device `std::`、struct 传值入 kernel…），带 `stop_and_report` / `remove_and_record` / `manual_implementation` 动作 |
| `schema.md` | API 映射记录的字段 schema（维护映射时的契约） |
| `rule_schema.md` | grammar/constraint 规则的字段 schema |
| `validation-checklist.md` | "可报告成功"的硬门禁清单 + 允许的最终状态标签 |
| `symbol_mapping.yaml` | **本项目自建**：header 层符号/宏/命名空间/路径映射（`_CCCL_API→_ASC_AICORE_FN` 等），外化自 `core/config.py` 的 segment_substitutions/MigrationPolicy，带 provenance。**这是迁移管线真正注入的表** |
| `assets/*-zh.md` | 中文工程文档模板（plan / readme / approval-message），官方 skill 工作流用于产出 per-operator 交付文档；本项目作降级方法论参考 |

> 注 1：官方 `SKILL.md`（迁移 workflow 全文 / 方法论 playbook）已移至 `skills/cuda2ascend-simt.SKILL.md`，与项目自有 skills 同处。它是**方法论参考**，非 `read_skill()` 加载的提示词。
> 注 2：官方原本的 `reference/example/`（runtime/kernel/torch 层 cuda↔simt 工程）已删除——它与本项目 header 层 `examples/`（few-shot 库）不同级、用不上，避免"example"概念混淆。

## 分层适用性（重要）

官方知识库的迁移层与本项目**不完全同级**，按可复用程度分三档使用：

1. **可直接查表（数据级复用）**：`device_api.yaml` 的 `device/math`、`device/type-conversion`、
   `device/comparison` 子集 —— 当某个 ASC-STL 算法/numeric 头编译进 kernel 后落到设备 intrinsic
   时，这里就是权威映射。`grammar_rules.yaml` 的设备修饰符规则同理（对应本项目 `_ASC_AICORE_FN`）。
2. **方法论/格式复用**：`schema.md` / `rule_schema.md` 的字段契约（`status`×`mapping_type`×`action`
   ×`fallback`×`source`×`reviewed_by`/`reviewed_at`）、`constraint_rules.yaml` 的降级分类法
   （downgrade/blocked/excluded）、`validation-checklist.md` 的硬门禁、`skills/cuda2ascend-simt.SKILL.md`
   的审批门 —— 这些是本项目当前缺的"可审计知识库"形态，应被吸收。
3. **跨层参考**：`runtime_api.yaml` 主体（cudaMalloc/stream/event…）—— 与头文件层不同级，
   作为背景参考，不直接搬进 header 迁移路径。

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
- **注入**：改写（`core/pipeline.py` `_rewrite`）与测试迁移（`core/test_migrator.py`
  `migrate_operator_tests`）在调模型前，按当前头涉及的符号 `render_block()` 出命中项，
  拼进提示词。always_inject 的符号映射对每个头都注入；语法/约束规则按**白名单触发词**
  （`double`/`complex`/`__device__`/`assert` 等）命中才注入，避免噪声。
- **验证**：`tests/test_knowledge_base.py` 离线单测覆盖加载/注入/触发/缺库降级。

## 待办（进一步收敛）

- 让 `core/config.py` 的 `segment_substitutions` 与 `MigrationPolicy` 默认值**从本库
  `symbol_mapping.yaml` 读取**，彻底消除"config 默认值 + yaml"两处来源（当前 yaml 为外化记录，
  运行期仍以 config 默认值为准）。
- 把官方 `api-mapping/` 的 `device/math`·`type-conversion`·`comparison` 子集接入 `knowledge_base`，
  当算法落到设备 intrinsic 时按需检索（体量大，仍不默认注入）。
