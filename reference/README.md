# reference/ — 分层、可审计的迁移知识库

`manifest.yaml` 是唯一知识源索引。目录把“具体事实”和“泛化规则”分开，避免为了支持一个新符号复制多条近似规则。

```text
reference/
├── manifest.yaml                 # 注册 mapping/rule/strategy/API 数据集
├── mappings/                     # 具体 CCCL → ASC 映射事实
│   ├── macros.yaml               # 宏和删除项
│   ├── namespaces.yaml           # 命名空间/限定名前缀
│   ├── includes.yaml             # include 形式和特殊系统头
│   ├── symbol_providers.yaml     # 无法按命名约定推导的 provider 例外
│   └── path_segments.yaml        # 路径段替换，如 __cccl → __asc
├── rules/                        # 可复用于任意符号/头文件的规则
│   ├── grammar.yaml              # 语法改写触发规则
│   ├── constraints.yaml          # unsupported/restricted 决策规则
│   ├── implicit_dependencies.yaml# 限定符号 → provider 头的泛化推导
│   └── migration_policy.yaml     # 延期、bootstrap、wrapper 策略
└── api-mapping/                  # 具体 runtime/device API 映射目录
```

## 两类知识的边界

### 具体映射 `mappings/`

只有无法从通用语法推导、确实需要逐项确认的事实放在这里，例如：

- `_CCCL_API → _ASC_AICORE_FN`；
- `_CUDA_VSTD:: → asc::std::`；
- `<cuda/std/detail/__config> → "asc/std/__config"`；
- `cudaMalloc → aclrtMalloc` 等 API 表记录。

具体映射带 `source`、`reviewed_by`、`reviewed_at`，用于审计。被 manifest 标记为 `inject: true` 的 header 映射会进入模型提示词；大型 API 表只注册、按需查询，不会整表注入。

### 泛化规则 `rules/`

规则描述“如何匹配、如何决策”，不枚举每个目标符号。例如 `implicit_dependencies.yaml` 捕获任意：

```text
_CUDA_VSTD::<symbol>(...)
cuda::std::<symbol>(...)
::cuda::std::<symbol>(...)
```

然后用真实 CCCL 源树的 header-stem 索引解析 provider：

```text
move(...)             → __utility/move.h
move_if_noexcept(...) → __utility/move.h（symbol_providers.yaml 具体例外）
forward<T>(...)       → __utility/forward.h
```

规则只对配置的基础 provider 模块生效，并在候选歧义时放弃推断，避免为了“多识别”破坏依赖图。无法按精确头名约定解析的少数例外，应新增到 `mappings/symbol_providers.yaml`，而不是打开模糊前缀匹配或复制 `_CUDA_VSTD/cuda::std/::cuda::std` 三种规则。

## 运行时接入

- `core/knowledge/reference_loader.py`：统一读取 manifest；兼容旧版三文件 fixture。
- `Config.load()`：从 manifest 注册的数据加载路径段、迁移策略和泛化隐含依赖规则，覆盖 settings 中的同名运行策略。
- `KnowledgeBase.load()`：合并可注入的具体 mappings，并按类型加载 grammar/constraint 规则。
- `core/analysis/inventory.py`：去除注释和字符串后执行泛化依赖规则，利用整棵源树的头文件索引解析 provider。
- `core/migration/pipeline.py`：把当前头命中的 mappings/grammar/constraints 注入改写请求。
- `core/testing/test_migrator.py`：用 ACCL 头和 CCCL 测试再次查询知识库，约束测试生成。

## 维护约定

- YAML 是 source of truth，Markdown 是说明或浏览视图。
- 具体事实放 `mappings/`，可复用行为放 `rules/`。
- 不要为同一语义的不同限定拼写复制规则；优先使用带捕获组的泛化规则。
- `mapped` 记录必须有证据和复核日期；证据不足时保留 `unknown/conditional`。
- API 表体量大，只按需查询，不默认污染 header 迁移提示词。
- 修改 manifest 或规则后运行 `pytest -q`，并检查真实 `dep-graph` 是否产生异常环。

字段约定见 `rule_schema.md` 和 `schema.md`。
