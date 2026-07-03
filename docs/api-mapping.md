# CCCL CUDA API → 晟腾 SIMT API 独立映射管线

`api-map` 不参与头文件迁移、测试生成或 ACCL 仓写入。它只读以下两棵树：

- `repos/cccl/libcudacxx/include/cuda`：同时覆盖 `cuda/std` 标准库层和 `cuda` 扩展层；
- `docs/SIMT-API`：晟腾侧 API 的唯一文档证据源。

管线先确定性枚举全部源文件和文档，再对每个源文件完整读入。超过上下文安全阈值的头文件按行分片，
相邻分片保留重叠行，随后按“名称 + 签名 + 源行”去重。每个分片执行两层检查：模型提取 API；
确定性候选扫描器要求模型逐条说明候选是 API、误报、重复还是条件声明。提取完成后，工具按 API 名称、
语义摘要、头文件类别和文档路径检索候选文档，模型只能从实际注入的文档中给出映射。

## 推荐启动顺序

先离线确认扫描范围，不调用模型：

```bash
python3 main.py api-map --prepare-only
```

用一个代表性头验证真实模型输出。`--include` 是相对于 `include/cuda` 的 glob，可重复：

```bash
python3 main.py api-map \
  --include '__cmath/sincos.h' \
  --real-ai --show-model-io
```

分别试跑标准库和扩展层的小批文件：

```bash
python3 main.py api-map --include 'std/__algorithm/*.h' --limit 5 --real-ai --show-model-io
python3 main.py api-map --include '__warp/*.h' --limit 5 --real-ai --show-model-io
```

确认结果后跑全树：

```bash
python3 main.py api-map --real-ai --show-model-io
```

全量运行默认可续跑。源文件 SHA-256、SIMT 文档集合指纹、分析 skill、模型名和管线版本都一致时，
已完成文件直接跳过；按 `Ctrl-C` 停止后执行相同命令即可继续。失败文件默认保留供人工检查，修正问题后用：

```bash
python3 main.py api-map --real-ai --retry-failed --show-model-io
```

要强制重算所有选中文件，增加 `--no-resume`。离线调度冒烟可用 `--mock`，但 mock 会把候选全部标为
非 API，不能作为真实映射结论。

使用不同 `--include` 分小批运行时，`api_mapping.md/json` 会累计汇总所有源码、文档和 skill 指纹仍然有效的
逐文件结果，不会只保留最后一批。`selected_files` 表示本次命令选中的文件数，`inventory_files` 表示全树文件数。
旧版本或源码已变化的逐文件结果仍保留在 `files/` 供审计，但不会混入当前总表。

## API 覆盖口径

模型只记录当前文件实现中引用的外部公开 CUDA/NV 平台 API（例如 `::__brevll`、`::sincosf`、
`::__half`、`::__half2float`），统一标为 `referenced`；同一外部 API 在同一头内重复调用只统计一次。
`cuda::` / `cuda::std::` 命名空间下的符号（例如 `::cuda::neg`、`::cuda::std::forward`、
`::cuda::std::sin`、type traits、alias 等）属于 libcudacxx 包内依赖，会随依赖闭包一起迁移，
不属于需要查询晟腾替代项的外部 SIMT API，因此必须在 coverage 中标为 `non_api`，不进入映射总表。
当前头自身声明或定义的公开接口是待迁移实现的目标，同样不进入映射总表。
宏（包括 header guard、特性开关和函数式 dispatch 宏）暂不统计。内部 helper 与实现级
声明只参与候选 coverage，不进入 API 总表。设备函数、host/device 函数、设备数据类型和设备代码可用的
编译期实体以及外部公开的 host-only CUDA runtime/driver 函数均纳入，host-only 函数通过 `device_support`
明确分类。名称为 `cuda*`/`CU*` 的 runtime/driver 句柄、结构体、设备属性/配置枚举与查询类型，以及状态常量
标为 `non_api`；即使类型被推断为 `host_device` 也不进入映射总表。`__half` 等设备数据类型不受此规则影响。
普通常量和枚举成员
不统计，但 `threadIdx`、`blockIdx` 等 CUDA 设备内置变量仍属于 API。以下划线开头不能单独作为过滤依据：
已有公开文档的 CUDA intrinsic 仍属于公开 API。

纯调用表达式、控制流、注释/字符串、仅由 `#include` 间接导出的符号不算本文件新 API。每个重载保留
独立签名。确定性扫描器不是 C++ 解析器，因此允许模型补充扫描器未捕获的 API；反过来，扫描器捕获的
每个候选必须出现在 coverage 台账中，缺一项则整次模型响应校验失败并自动重试。

映射状态分为：

- `exact`：语义与约束足以直接对应；
- `partial`：类型、范围、执行域或边界行为较窄/较宽；
- `semantic`：概念对应或需组合多个晟腾 API；
- `uncertain`：候选相关但文档证据不足；
- `no_match`：本地 SIMT 候选文档中没有有证据的对应项。

`no_match` 不表示晟腾平台绝对不支持，只表示当前 `docs/SIMT-API` 没有支持该映射的本地证据。

## 输出

所有产物位于 `outputs/api_mapping/`：

- `api_mapping.md`：简洁的六列表格，只包含 CCCL API、来源头文件、ACCL API、文档链接、匹配等级和功能简介；
- `api_mapping.json`：同一结果的机器可审计版本，保留签名、设备属性、可见性和映射说明；
- `source_inventory.json`：全量源文件的层级、大小、行数和 SHA-256，并单列本次命令选中的路径；
- `docs_index.json`：SIMT 文档标题、heading、符号目录和整体指纹；
- `files/*.json`：逐源文件成功/失败状态，是断点续跑的最小事务单元；
- `model_io/<file-id>/`：每次提取和映射的完整请求/响应，便于复核漏项或误映射。

常用调节参数可通过 `python3 main.py api-map --help` 查看。大生成头优先调小
`--max-source-chars`，不要为了减少请求数把它调到超过模型上下文；文档召回不足时可适当提高
`--top-docs-per-api` 和 `--max-docs-per-mapping-call`。
