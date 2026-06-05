# ASC_agent 开发路线（下一步方向）

本文件记录已识别、但**尚未实现**的方向，供后续迭代。已落地的修复见 `README.md` /
`docs/guide.md` 与对应单测。

## 近期已落地（摘要）

- **止血**：失败分类 env/code（`core/failure_triage.py`）+ 环境自愈（`core/build_env.py`）+
  修复循环去重/早停 + 缺 `cannsim` 标 SKIPPED——环境问题不再空烧模型调用。
- **模型工具**（默认关闭）：`core/agent_tools.py` 让修复模型可读 sibling 头 / grep 符号 /
  `g++ -fsyntax-only` 自检 / 抽日志 error 行；工具循环见 `model_client.generate_with_tools`。
- **提示词单一事实源**：`skills/_shared/` 片段 + `{{include:}}`；合并两个 rewrite_fix。
- **脚手架统一化**：host/kernel/full 运行脚本由 `core/scaffold_scripts.py` 生成、共用
  `core/scaffold_env.py` 环境片段；删除签入的 `000`–`004` 脚本。
- **合成复杂算子**：`sort3`（3 输入 / 3 输出、分支排序网络、整数精确）入源仓与批量清单，
  用于压测迁移管线的多 IO / dtype / 独立 golden。

---

## R1. 传递依赖迁移（单文件迁移 → 依赖闭包迁移）

### 问题

当前迁移以**单个头文件**为单位：`convert --input <one header>` 只生成那一个 ACCL 头，
不解析它 `#include` 的其它 CCCL 头，也不会把这些依赖一并迁移。

于是凡是**跨头依赖**的算子，kernel 侧一编译就断在缺失的依赖上。实测案例（`minmax`）：

```
minmax.h:10:10: fatal error: 'ascend/std/__utility/pair.h' file not found
        #include "ascend/std/__utility/pair.h"
```

`minmax` 依赖 `pair`，而 `__utility/pair.h` 从未被迁移。该算子只是“恰好”被改成了
**内联自带 `pair` 结构**才绕过去；对真正需要复用 `pair` / `type_traits` /
`__config` 之外其它公共头的算子，这条路会持续踩坑。

> 注：host 侧有时能过，是因为 host 构建用的是仓库完整 include 树；kernel 构建走的是
> `run_test.sh` 里 `ascend -> include/ascend` 的符号链接子集，缺哪个依赖就直接断。
> 两侧 include 解析口径不一致，会放大这个问题。

### 目标

把迁移单位从“单文件”升级为“**依赖闭包**（dependency closure）”：给定一个入口 CCCL 头，
自动发现并按拓扑序迁移它在 `libcudacxx/include/cuda/std` 内的全部传递依赖。

### 设计草案

1. **依赖解析器（新模块 `core/dep_graph.py`）**
   - 解析 CCCL 头里的 `#include "cuda/std/..."`（含 `<cuda/std/...>`），用 `mapping`
     规则筛出落在 `source_repo_prefix` 内的“仓内依赖”，忽略标准库/系统头。
   - 递归构建有向图，检测环（C++ 头允许 include guard 形成的“逻辑环”，按已访问集合截断）。
   - 产出拓扑序（叶子优先）。
2. **批量迁移编排（扩展 `core/pipeline.py`）**
   - 入口头触发时，先迁移其依赖闭包（叶子→根），每个头复用现有 `_rewrite` 流程；
   - 路径/guard 仍由 `path_mapper` 推导（`__utility/pair.h` → `ascend/std/__utility/pair.h`），
     段替换规则沿用 `segment_substitutions`。
   - 已迁移过的头跳过（按 `target_relpath` 去重），避免重复调用模型。
3. **迁移产物自洽校验（扩展 `core/operator_test.py` 或新增 `verify_includes`）**
   - 在跑 kernel 测试前，做一次**纯头自包含编译**（`g++ -fsyntax-only -I include`），
     提前抓出“缺依赖/路径不一致”，而不是等到 cannsim 阶段才暴露。
   - kernel 符号链接子集应覆盖依赖闭包涉及的所有子目录。
   - 注：`core/agent_tools.py` 的 `host_syntax_check` 已提供“`g++ -fsyntax-only` 自检”这一
     building block，可作为该校验的复用基础（当前仅供模型在修复时按需调用）。
4. **失败闭环接入**
   - 若某依赖迁移后仍编不过，把缺失 include 的报错回传模型（复用 `fix_once` 的反馈修复），
     或在 `notes` 中标注“需要先迁移 X”。

### 验收

- 对 `minmax`（依赖 `pair`）：不内联 `pair`，而是自动迁移出 `__utility/pair.h`，
  kernel 侧 `#include "ascend/std/__utility/pair.h"` 能解析、能编译、能过 cannsim。
- 增补单测：构造一个“A 依赖 B 依赖 C”的 mock 头三元组，断言迁移顺序为 C→B→A 且产物齐全。

### 影响面 / 风险

- 模型调用次数随依赖数线性增加（成本上升）；可加“仅迁移缺失依赖”的增量模式。
- CCCL 真实依赖很深（`__config` / `__type_traits/*`），需设“迁移边界”白名单，
  对边界外的基础设施头采用**手写一次、长期复用**的策略，而非每次让模型重迁。

---

## 其它备忘（未来再细化）

- 迁移产物的 host / kernel **两侧 include 解析口径统一**（见 R1 注）。
- `gcd` / `lcm` / `midpoint` 等整数算子已可借 `kernel_spec.dtype=int*` 测；
  后续补它们的 CCCL→ACCL 迁移与 few-shot 示例。
