# ASC_agent

ASC_agent 是一个面向 **CCCL/libcudacxx -> ACCL/asc-stl** 的迁移与验证助手。它读取
`repos/cccl/libcudacxx/include/cuda/std` 下的 CCCL 头文件，生成对应的
`repos/accl/asc-stl/include/asc/std` 头文件，并可继续迁移算子测试，在 host 侧和
AscendC kernel 仿真侧验证结果。

## 能做什么

- 迁移单个 CCCL 头文件，自动推导 ACCL 目标路径和 header guard。
- 调用模型生成 ACCL 头文件，并结合 `examples/` few-shot 示例与 `reference/` 可审计知识库。
- 迁移 CCCL 测试为 ACCL host 测试和 kernel `kernel_spec`。
- 运行 host C++ 测试和 AscendC/cannsim kernel 仿真测试，并区分语义通过与 smoke 冒烟。
- 根据测试失败日志回灌模型，修复 header、host 测试或 kernel spec。
- 按依赖闭包迁移跨头依赖算子，自动按叶子优先顺序处理 include 依赖与源码符号隐含依赖。
- 扫描一个源侧文件夹，按依赖、复杂度、测试映射和迁移状态生成首批/后续迁移建议，人工确认后再执行。
- 对整库做依赖分析（不调用模型），输出严格按依赖波次分批的迁移台账；迁移成功自动标记，可增量续跑。
- 将已验证产物晋升为 `examples/` 金标准示例，并维护 manifest 元数据索引。

## 快速命令

> 调用模型的命令示例默认带 `--show-model-io`，用于实时查看完整模型交互；不想刷屏时去掉即可。
> 没有 CANN/cannsim 的机器可以加 `--host-only`；想更快检查 kernel 可以加 `--kernel-fast`。

```bash
# 离线自检，不需要 API key 或 CANN。
python3 main.py selftest

# 迁移一个 CCCL 头文件并写入 ACCL 目标仓（transform 为真实 libcudacxx 算子样例之一）。
python3 main.py convert --input repos/cccl/libcudacxx/include/cuda/std/__algorithm/transform.h --show-model-io

# 迁移并运行 host/kernel 测试；失败会回灌模型修复。
python3 main.py convert --input <header> --with-tests --test-feedback-to-model --show-model-io

# 对已经迁移好的目标生成/运行测试。
python3 main.py test --input <header> --show-model-io

# 把已迁移并验证的算子晋升为 examples/ 金标准示例（不带参数则列出候选）。
python3 main.py make-example clamp sort3 quad_fanout

# 扫描一个源侧文件夹，先生成首批/后续迁移建议，确认后再执行首批。
python3 main.py folder-plan --source-dir std/__algorithm --cccl-repo repos/cccl --real-ai --show-model-io
python3 main.py folder-migrate --plan outputs/folder_migration_plan.json --batch first --approve \
    --real-ai --with-tests --test-feedback-to-model --show-model-io

# 对整库做依赖分析并按依赖波次分批（不调用模型），再按波次顺序迁移、成功自动标记。
python3 main.py package-plan --cccl-repo repos/cccl
python3 main.py package-migrate --plan outputs/package_migration_plan.json --batch next --approve \
    --real-ai --with-tests --test-feedback-to-model --show-model-io

# 按依赖闭包迁移一个跨头依赖的算子（叶子优先；先看计划加 --plan-only，真实迁移加 --real-ai）。
# adjacent_find 为真实 libcudacxx 闭包样例：adjacent_find → comp → integral_constant。
python3 main.py dependency-convert --entry-header __algorithm/adjacent_find.h --cccl-repo repos/cccl \
    --real-ai --with-tests --test-feedback-to-model --show-model-io

# 只看头文件依赖图与迁移顺序（include 依赖 + reference 声明的符号隐含依赖）。
python3 main.py dep-graph --cccl-repo repos/cccl
```

## 目录速览

```text
ASC_agent
├── main.py                 CLI 瘦入口：解析参数并分发到 cli/
├── cli/                    CLI 实现：commands（子命令）/ helpers（共享辅助）/ parser（参数装配）
├── config/                 settings.yaml（std 层）/ settings.cuda.yaml（cuda 扩展层）与批量清单
├── core/                   核心代码（按职责分包）：
│   ├── common/             配置与通用工具（config / utils）
│   ├── llm/                模型客户端 / 取证工具 / best-of-N
│   ├── knowledge/          可审计知识库与 few-shot 检索
│   ├── analysis/           清单 / 依赖图 / 测试索引 / 迁移状态与上下文
│   ├── planning/           文件夹级迁移规划 / 整库分波次规划（package_planner）
│   ├── migration/          头改写 / 修复 / 示例晋升
│   ├── testing/            测试迁移 / 执行 / 脚手架 / 环境自愈 / 自包含校验
│   └── repo/               git 提交与 push 校验
├── skills/                 模型提示词与共享契约片段
├── reference/              可审计迁移知识库：符号映射、语法规则、约束规则、API 映射资料
├── examples/               few-shot 金标准示例
├── repos/cccl              CCCL 源侧样例仓
├── repos/accl              ACCL 目标仓与生成测试
├── tests/                  离线 pytest 单测
├── docs/                   更完整的指南、结构说明与路线图
└── outputs/                模型请求/响应、生成产物、host/kernel 测试日志
```

## 核心流程

```text
CCCL 头文件
  -> core/analysis/path_mapper.py 推导目标路径与 header guard
  -> core/knowledge/knowledge_base.py 从 reference/ 注入命中的映射/语法/约束规则
  -> core/knowledge/example_retrieval.py 从 examples/ 选择 few-shot 示例
  -> core/migration/pipeline.py 调模型生成 ACCL 头文件
  -> core/testing/test_migrator.py 可选生成 host 测试与 kernel_spec
  -> core/testing/operator_test.py 可选运行 host/kernel 测试
  -> core/migration/fix_once.py 可选根据失败日志修复并重测
```

关键输出：

- `outputs/model_request.md`：头文件迁移时发给模型的请求。
- `outputs/rewritten_target.h`：模型生成的头文件初稿。
- `outputs/rewrite_result.json`：本轮迁移结果。
- `outputs/host_test_<op>.log` / `outputs/kernel_test_<op>.log`：测试日志。
- `outputs/folder_migration_plan.json` / `.md`：文件夹级首批与后续迁移建议。
- `outputs/dependency_convert_report.json`：依赖闭包迁移报告。
- `outputs/migration_state.json`：已验证迁移状态，用于闭包增量跳过；只记录 semantic pass，不记录 smoke。

## reference/ 怎么参与迁移

`reference/` 不是整库塞进 prompt，而是按当前任务命中项注入：

- `reference/symbol_mapping.yaml`：头文件层符号/宏/命名空间/include/header guard 映射，例如
  `_CCCL_API -> _ASC_AICORE_FN`、`cuda::std -> asc::std`；其中 `symbol_dependencies`
  声明源码符号隐含依赖，例如 `_CUDA_VSTD::move -> __utility/move.h`，用于依赖图和迁移闭包。
- `reference/grammar_rules.yaml`：语法改写规则，例如 `__device__`、`__shared__`、`assert`、`printf`。
- `reference/constraint_rules.yaml`：受限或不支持特性，例如 `double`、`complex`、texture、cooperative groups。

接入点：

- 头文件迁移：`core/migration/pipeline.py` 调用 `load_knowledge_base(...).render_block(source_text)`，
  并把结果写进 `outputs/model_request.md`。
- 测试迁移：`core/testing/test_migrator.py` 用已迁移头和 CCCL 测试内容查询知识库，再拼进测试迁移请求。
- 策略来源：`Config.load()` 会从 `reference/symbol_mapping.yaml` 读取
  `segment_substitutions` / `migration_policy` / `symbol_dependencies` 并覆盖进运行时 config；
  `settings.yaml` 不再维护这三类迁移策略。

`reference/api-mapping/` 当前主要作为 runtime/device API 层的资料储备与方法论参考，还没有默认注入
ASC-STL 头文件迁移路径。

## 测试模型

host 测试是每个算子独立生成的完整 C++ 文件。kernel 测试由固定 AscendC/ACL/cannsim 脚手架加
模型填充的 `kernel_spec` 组成：

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

`kernel_spec` 支持 1 到 8 个 GM 输入、1 到 8 个 GM 输出。`golden_code` 必须是独立参考实现，
禁止调用被测的 `asc::std::*`。测试迁移不可用时，少数已知形状算子（如 `generate` / `for_each`）
会使用内置语义 fallback；未知形状只做 include/build/launch 冒烟，不猜测 `op(x, y)` 调用，也不计为语义通过。
测试结果会显式区分 `semantic_passed` 与 `smoke_passed`；`migration_state.json` 只接受语义通过。

测试失败会先由 `core/testing/failure_triage.py` 分成环境类和代码类：环境类直接报告或跳过修复循环，代码类才回灌模型。
`core/testing/build_env.py` 会在测试前处理部分常见环境问题，例如过期 CMake 缓存和 CANN 工具 PATH。

## 模型工具

`model.tools_enabled: true` 时，模型在生成或修复前可以使用工具取证和自检：

- `read_repo_file`：读取 sibling 头、`__config` 等仓内文件。
- `grep_repo`：检索宏、符号和调用点。
- `host_syntax_check`：用 `g++ -fsyntax-only` 做 host 语法自检。
- `extract_error_lines`：从大日志抽取关键错误行。

这些工具覆盖头文件初稿生成、测试迁移和测试反馈修复三条路径。`provider=mock` 时自动关闭，离线流程不受影响。

## 示例库维护

few-shot 检索依赖 `examples/` 的质量。已迁移并通过测试的算子可以晋升为金标准示例：

```bash
python3 main.py make-example                      # 列出可晋升候选
python3 main.py make-example clamp sort3 minmax    # 晋升指定算子
python3 main.py make-example --all --overwrite     # 全量刷新
```

晋升会复制 CCCL 源头、ACCL 头、CCCL 测试、ACCL host 测试和 kernel_spec 到 `examples/headers` 与
`examples/tests`，并同步更新 `examples/manifest.yaml`。晋升前会做质量门禁：header guard、host 测试
失败时返回非零、kernel_spec 字段合法。

运行时 few-shot 检索优先读取 `examples/manifest.yaml`，用 `id`、`source_header`、`target_relpath`、
`shape`、`tags` 等元数据加示例内容共同排序；没有 manifest 的临时示例目录仍会回退到文件扫描。

## 文件夹级智能规划

`folder-plan` 用于从“我指定某个文件”升级为“我指定某个源侧目录”。推荐按原库目录写
`std/__algorithm`、`std/__numeric` 这样的子目录；工具会映射到
`libcudacxx/include/cuda/std/...` 下对应范围，合成 inventory、测试索引、依赖图和现有迁移状态，
并输出可审阅计划：

```bash
python3 main.py folder-plan --source-dir std/__algorithm --cccl-repo repos/cccl --real-ai --show-model-io
```

也兼容绝对路径、`cuda/std/__algorithm`、`libcudacxx/include/cuda/std/__algorithm` 和旧的 `__algorithm` 写法。

输出默认写到 `outputs/folder_migration_plan.json`、`outputs/folder_migration_plan_details.json`
和 `outputs/folder_migration_plan.md`。其中 `folder_migration_plan.json` 是执行用轻量计划，
保留跨包依赖预览和计数；完整依赖闭包与全量外部依赖明细在 details JSON。
计划会扫描整个 CCCL `cuda/std` 依赖图和 ACCL `asc/std` 目标头：

- 包内依赖会正常参与排序。
- 包外依赖会按已验证满足、目标存在但未验证、目标 include 断裂、目标缺失、策略延期/覆盖分组。
- 无依赖闭包的 pending 头会单独列入 `independent_leaf_candidates`，适合先作为低耦合批次推进。
- 需要跨包扩展的头会列入 `external_dependency_decisions`，默认不会进入推荐首批。
- Markdown 只展示摘要、top 依赖和少量 header 样本，避免把大型闭包完整铺开。

JSON 默认 `approved: false`，所以执行端不会因为模型建议就自动迁移；人工审阅后再运行：

```bash
python3 main.py folder-migrate --plan outputs/folder_migration_plan.json --batch first --approve \
    --real-ai --with-tests --test-feedback-to-model --host-only
```

如果你明确接受本批次顺带迁移 source-dir 范围外的未验证/缺失依赖，再额外加：

```bash
python3 main.py folder-migrate --plan outputs/folder_migration_plan.json --batch __algorithm/foo.h \
    --approve --real-ai --allow-external-dependencies --with-tests --test-feedback-to-model
```

常用批次：

- `--batch first`：执行推荐首批。
- `--batch followup-1`：执行某个后续批次。
- `--batch all`：执行首批和所有后续批次。
- `--batch __algorithm/clamp.h,__algorithm/min.h`：执行显式 header 列表。

`--mock` 只使用确定性启发式推荐，适合离线检查；`--real-ai` 会把有界元数据交给模型做排序和风险说明。
模型输出会被过滤，只能选择扫描结果中真实存在、仍处于 pending、未命中依赖环且未已有目标文件的 header。
真正迁移时，`folder-migrate` 对每个 header 继续复用 `dependency-convert`，因此 leaf-first 闭包迁移、
`--with-tests`、`--test-feedback-to-model`、`--verify-includes` 等能力仍然生效。
实际执行默认会拒绝需要跨包扩展的批次；`--plan-only` 可安全查看完整闭包计划，不触发这个审批门。

## 整包分波次规划（package-plan / package-migrate）

单入口闭包迁移（`dependency-convert`）一次只处理一个头的依赖闭包，依赖多时模型一次要面对一大串
尚未就绪的依赖；`folder-plan` 的后续批次只是按复杂度定长切块，**并不严格保证「我的依赖都在更早
批次」**。`package-plan` 针对整库做依赖分析（**不调用模型**），输出**严格按依赖波次（wave）分批**的
计划：batch-1 是叶子，batch-N 只依赖更早批次，因此按批次顺序喂给模型时，每个头的依赖都已就绪。

报告是一个**可持久化、可增量**的台账：每当头文件迁移成功（host/kernel 语义测试通过，记录在
`outputs/migration_state.json`）就自动标记为已完成；重跑 `package-plan` 时已完成的头会从波次中
剔除，其下游自动提前解锁。强连通分量（环）成员会被放进同一批次共同迁移并标 `contains_cycle`。

```bash
# 1) 生成/刷新整库分波次计划（无模型；写 outputs/package_migration_plan.{json,md}）。
python3 main.py package-plan --cccl-repo repos/cccl

# 2) 人工审阅 markdown 后，按波次推进。--batch next = 首个仍有未完成头的波次。
python3 main.py package-migrate --plan outputs/package_migration_plan.json --batch next --approve \
    --real-ai --with-tests --test-feedback-to-model --show-model-io

# 3) 迁移成功的头会自动回写标记；重跑 package-plan 即可看到 completed 增长、波次收缩。
python3 main.py package-plan --cccl-repo repos/cccl

# 手动把某些头标记为已完成 / 撤销标记（持久化，与自动证据合并）。
python3 main.py package-plan --mark __algorithm/clamp.h,__numeric/gcd.h
python3 main.py package-plan --unmark __numeric/gcd.h
```

`--batch` 取值：`next`（推荐，自动推进下一波）/ `all` / `batch-1`、`batch-2` / 逗号分隔 header 列表。
`package-migrate` 对每个头复用 `dependency-convert`，因此 leaf-first 闭包、`--with-tests`、
`--test-feedback-to-model`、`--verify-includes[-strict]`、`--defer-dependents-on-failure` 等能力全部生效；
批次结束后会自动刷新台账（把新通过的头标记为已完成）。先 `--plan-only` 可只看每个头的闭包计划、不调模型。
命中 `migration_policy` 的延期上游/伞头不进波次，单列在计划的 deferred 区。`--settings config/settings.cuda.yaml`
下同样可对扩展层整包规划。

## 依赖闭包迁移

`dependency-convert` 用于迁移跨头依赖算子。它从入口头解析 `cuda/std` 内的仓内 include，并结合
`reference/symbol_mapping.yaml` 的 `symbol_dependencies` 识别源码符号隐含依赖。例如源头只写了
`_CUDA_VSTD::move`、没有显式 include `cuda/std/__utility/move.h`，依赖图仍会把 `__utility/move.h`
放进闭包并排在使用者之前迁移。闭包按叶子优先顺序迁移，并复用已验证且源哈希未变的依赖。

```bash
# 先看计划（不调模型、不写盘）——adjacent_find 为真实 libcudacxx 闭包样例。
python3 main.py dependency-convert --entry-header __algorithm/adjacent_find.h --cccl-repo repos/cccl --plan-only
# 真实迁移整条闭包并写入 ACCL（叶子优先序：integral_constant → comp → adjacent_find），失败先回灌模型修复。
python3 main.py dependency-convert --entry-header __algorithm/adjacent_find.h --cccl-repo repos/cccl \
    --real-ai --with-tests --test-feedback-to-model --show-model-io

# 一条命令：按依赖闭包 leaf-first 改写，并紧跟每个算子跑 host(+kernel) 测试。
# 默认先把代码类测试失败回灌模型修复；修复后仍失败时，--defer-dependents-on-failure
# 只延期失败头的下游、独立分支继续；--continue-on-test-failure 则后续算子也继续尝试；
# --verify-includes[-strict] 在每个头改写后做自包含 include 编译自检。
python3 main.py dependency-convert --entry-header __algorithm/adjacent_find.h --cccl-repo repos/cccl \
    --real-ai --with-tests --host-only --test-feedback-to-model --verify-includes --show-model-io
```

### 更多入口头迁移示例（按复杂度递增）

> 入口头路径相对 `cuda/std`，例如 `__algorithm/clamp.h` → `repos/cccl/libcudacxx/include/cuda/std/__algorithm/clamp.h`。
> 把上游 libcudacxx 整仓落到 `repos/cccl/libcudacxx/` 后，任意真实算子头都能用同一套命令迁移。

```bash
# 叶子 type_trait：无 in-tree 依赖，最快端到端跑通（host 测试即可）。
python3 main.py dependency-convert --entry-header __type_traits/integral_constant.h \
    --cccl-repo repos/cccl --real-ai --with-tests --host-only --test-feedback-to-model --show-model-io

# 单依赖算子：clamp → comp，host+kernel 全测并在失败时回灌模型修复。
python3 main.py dependency-convert --entry-header __algorithm/clamp.h \
    --cccl-repo repos/cccl --real-ai --with-tests --test-feedback-to-model --show-model-io

# 数值算子 gcd：先 --plan-only 看依赖序，确认后再真实迁移并做自包含 include 自检。
python3 main.py dependency-convert --entry-header __numeric/gcd.h --cccl-repo repos/cccl --plan-only
python3 main.py dependency-convert --entry-header __numeric/gcd.h \
    --cccl-repo repos/cccl --real-ai --with-tests --test-feedback-to-model --verify-includes --show-model-io

# 多依赖闭包 minmax：失败只延期下游、独立分支继续，自包含失败计为失败。
python3 main.py dependency-convert --entry-header __algorithm/minmax.h \
    --cccl-repo repos/cccl --real-ai --with-tests --test-feedback-to-model --defer-dependents-on-failure \
    --verify-includes-strict --show-model-io

# 扩展层入口 functional/identity：host-only + 失败回灌，适合无 CANN 的机器。
python3 main.py dependency-convert --entry-header __functional/identity.h \
    --cccl-repo repos/cccl --real-ai --with-tests --host-only --test-feedback-to-model --show-model-io
```

从零开始跑闭包前，可以清空已迁移算子头；保留手写 `__config` 与无扩展名伞头：

```bash
# 清空已迁移算子头（可随时 git restore 恢复）
find repos/accl/asc-stl/include/asc/std -name '*.h' -delete
# 如需连同已生成的测试一起重置，给迁移命令加 --overwrite-tests 即可（无需手删 test/）
```

常用选项：

- `--with-tests`：每个头迁移后立即迁移并运行测试；README 示例默认同时打开 `--test-feedback-to-model`。
- `--test-feedback-to-model`：代码类测试失败时回灌模型修复，避免第一轮测试失败就直接停下。
- `--host-only` / `--kernel-only` / `--kernel-fast`：控制测试范围。
- `--verify-includes`：迁移后做单头自包含编译检查。
- `--verify-includes-strict`：把自包含失败计为失败。
- `--defer-dependents-on-failure`：只延期失败头的下游，独立分支继续迁移。

## cuda/ 扩展层（非 std）迁移

CCCL `libcudacxx/include/` 下有两棵并列子树，命名空间不同：

```text
libcudacxx/include/cuda/std/   (cuda::std，标准库层)   -> asc-stl/include/asc/std/   (asc::std)
libcudacxx/include/cuda/       (cuda::，CUDA 扩展层)    -> asc-stl/include/asc/       (asc::)
```

默认的 `config/settings.yaml` 只迁 `cuda/std` 层。扩展层（如 `cuda/__utility/in_range.h`、
`cuda/__cmath/`、`cuda/__memory_resource/` 等 36 个 `__` 目录）的目标目录骨架已在
`asc-stl/include/asc/` 下用 `.gitkeep` 占位补齐，并提供独立配置 `config/settings.cuda.yaml`
把前缀映射改为 `cuda -> asc`、`cccl_test_prefix` 改为 `.../test/libcudacxx/cuda`。

> `--settings` 是**全局参数，必须放在子命令之前**：`python3 main.py --settings <file> convert ...`。

```bash
# 迁移单个 cuda/ 扩展头（in_range 为你正在看的样例）。--mock 可离线自检前缀映射。
python3 main.py --settings config/settings.cuda.yaml convert \
    --input repos/cccl/libcudacxx/include/cuda/__utility/in_range.h --show-model-io

# 迁移后为该扩展头生成/运行 host(+kernel) 测试（测试树取自 cuda/ 并列 test 子树）。
python3 main.py --settings config/settings.cuda.yaml convert \
    --input repos/cccl/libcudacxx/include/cuda/__bit/bitmask.h --with-tests --test-feedback-to-model --show-model-io

# 也可对已迁移的扩展头单独跑测试。
python3 main.py --settings config/settings.cuda.yaml test \
    --input repos/cccl/libcudacxx/include/cuda/__utility/in_range.h --host-only --show-model-io
```

依赖感知命令同样支持扩展层：扫描根已参数化（由 `source_repo_prefix` 推导 include 命名空间
`cuda/std` 或 `cuda`），`dep-graph` / `inventory` / `test-index` / `folder-plan` /
`dependency-convert` / `migration-status` / `migration-context` 都能落到 `cuda/` 层。
扩展层的依赖闭包会**跨层**自然纳入它依赖的 `cuda/std` 头（叶子优先一并排序）。

```bash
# 看整个 cuda/ 扩展层（含其依赖的 std 头）的依赖图与迁移顺序。
python3 main.py --settings config/settings.cuda.yaml dep-graph --cccl-repo repos/cccl

# 看某个扩展头的 leaf-first 闭包（in_range 的闭包会跨层拉入 std/__cmath/isnan.h 等）。
python3 main.py --settings config/settings.cuda.yaml dependency-convert \
    --entry-header __utility/in_range.h --cccl-repo repos/cccl --plan-only

# 扫描一个扩展层子目录并出迁移规划（--source-dir 写 __cmath / cuda/__cmath / 绝对路径均可）。
python3 main.py --settings config/settings.cuda.yaml folder-plan \
    --source-dir __cmath --cccl-repo repos/cccl --mock
```

> 注意：扩展头的闭包通常较大（`cuda::` 扩展大量依赖 `cuda::std`），整条真实迁移开销高；
> 建议先 `--plan-only` 审阅闭包，再决定批次。此外 `reference/symbol_mapping.yaml` 的符号映射
> 主要面向 `cuda::std`，扩展层 `cuda::`（非 std）符号可能需要补充规则后迁移质量才稳。

## 配置与环境

- 主配置：`config/settings.yaml`（`cuda/std` 标准库层），缺省值在 `core/common/config.py`。
- 扩展层配置：`config/settings.cuda.yaml`（`cuda/` 非 std 扩展层，前缀映射 `cuda -> asc`），
  用 `--settings config/settings.cuda.yaml`（放在子命令前）启用，详见上一节。
- 迁移策略：`reference/symbol_mapping.yaml`，其中 `segment_substitutions`、`migration_policy`
  与 `symbol_dependencies` 是运行时事实源。
- 源仓路径：`paths.cccl_repo`，默认 `repos/cccl`。
- 目标仓路径：`paths.accl_repo`，默认 `repos/accl`。
- 输出目录：`paths.output_dir`，默认 `outputs`。
- 知识库目录：`paths.reference_dir`，默认 `reference`。
- kernel SOC：`tests.kernel_soc_version` / `tests.kernel_cannsim_soc_version`，需与本机 CANN 匹配。

本机 CANN(cann-9.0.0) 使用 `Ascend950PR_9599`，cannsim 使用 `Ascend950`。换机器后如果 CMake 报
`SOC_VERSION ... does not support`，按该机 CANN 支持列表调整这两个值。

## 开发与 CI

- `pyproject.toml`：pytest 与 ruff 配置。
- `.github/workflows/ci.yml`：push / PR 上跑离线单测和 `selftest`，不调模型、不需要 CANN。
- 环境依赖型用例在数据或工具缺失时会跳过，保证干净检出可跑通基础测试。

更完整的安装、工作流和测试逻辑见 [docs/guide.md](docs/guide.md)；ACCL/STL 目录结构见
[docs/accl-stl-structure.md](docs/accl-stl-structure.md)；后续方向见 [docs/roadmap.md](docs/roadmap.md)。
