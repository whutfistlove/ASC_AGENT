# repos/ — ASC_agent 内置的源仓库与目标仓库

为了让「CCCL→ACCL 转换 + 测试迁移 + host/kernel 仿真测试」整条链路在**单一项目内**跑通，
这里内置了两个仓库（各放了几个示例文件）。目标仓采用 **方案 B（path == namespace）** 布局：
头文件路径前缀与命名空间前缀一致 —— `include/asc/std/…` ↔ `asc::std`。

```text
repos/
├── cccl/                                  # 源仓库（libcu++ 风格，保留 cuda 命名）
│   └── libcudacxx/
│       ├── include/cuda/std/
│       │   ├── __algorithm/{max,min,swap,clamp,minmax,quad_fanout,sort3,median3}.h
│       │   │                                  # 算子头（待迁移；median3 为新增的未迁移示例）
│       │   ├── __numeric/{gcd,lcm,midpoint,abs_diff,range_width,spread3,saturate_sub}.h
│       │   │                                  # 数值算子（saturate_sub 为新增的未迁移示例）
│       │   ├── __functional/identity.h
│       │   └── __cccl/{arch,os}.h             # 宏类头文件示例
│       └── test/libcudacxx/std/                          # CCCL 侧测试（语义基准，给模型迁移）
│           ├── __algorithm/<op>.pass.cpp      # 头 <op>.h ↔ 测试 <op>.pass.cpp
│           └── __numeric/<op>.pass.cpp
└── accl/                                   # 目标仓库容器（agent 的 ACCL_REPO）
    ├── .clang-format / CPPLINT.cfg / .pre-commit-config.yaml
    ├── scripts/                            # 版权头 hook + CANN 风格检查脚本
    └── asc-stl/                            # 库本体（对标 libcudacxx，仓名取自官方 CANN/asc-stl）
        ├── run_host_test.sh / run_kernel_full.sh  # 由脚手架生成（core/scaffold_scripts.py），勿手改
        ├── CMakeLists.txt                  # 顶层（INTERFACE 头文件库 + 测试）
        ├── include/asc/std/               # 目标头文件（namespace asc::std；含 __config + 各算子头）
        │   ├── __algorithm/  __numeric/  __functional/  __type_traits/  __utility/
        │   └── algorithm numeric functional type_traits utility   # 无扩展名“伞头”
        └── test/asc-stl/                   # host / device / kernel 测试（CMake 自动扫描）
            └── asc/
                ├── host/<algo>_tests.cpp           -> ctest 名 host.<algo>
                ├── device/<algo>_tests.cpp
                └── kernel/<algo>_example/run_test.sh -> ctest 名 kernel.<algo>.sim
```

## 关键约定

- **源前缀**：`libcudacxx/include/cuda/std`，**目标前缀**：`asc-stl/include/asc/std`，
  目录段 `__cccl → __asc`（见 `config/settings.yaml` 的 `mapping`）。
- **命名空间 / 宏**：目标头位于 `asc::std`，由 `_ASC_STD_BEGIN` / `_ASC_STD_END`
  （定义于 `asc/std/__config`）展开为 `namespace asc { namespace std {`；
  设备侧函数用 `_ASC_AICORE_FN` 修饰（host 下退化为 `inline`，CCE 下为 `__aicore__ inline`）。
- **CCCL 测试前缀**：`libcudacxx/test/libcudacxx/std`，后缀 `.pass.cpp`：算子头 `__algorithm/<op>.h` 的测试源
  约定为 `libcudacxx/test/libcudacxx/std/__algorithm/<op>.pass.cpp`（见 `mapping.cccl_test_prefix`）。
- 转换后的目标文件会写到 `accl/<target_relpath>`，例如
  `repos/accl/asc-stl/include/asc/std/__algorithm/min.h`。
- **测试代码由大模型按算子迁移**（CCCL 测试 → ACCL host 测试 + kernel_spec），不再是写死模板；
  host 测试逐条打印数值、kernel 测试 = 固定脚手架 + 模型槽位。详见 [../docs/guide.md](../docs/guide.md)。
- host 测试：CMake 扫描 `asc/host/*_tests.cpp`，用例名 `host.<algo>`。
- kernel 仿真：CMake 扫描 `asc/kernel/*_example/run_test.sh`，用例名 `kernel.<algo>.sim`，
  内部用 `cannsim` 跑仿真。
- host 端编译/链接只依赖标准 C++，可在普通 Linux 上跑；
  kernel 仿真需要 CANN 工具链 + `cannsim`（通常在 Ascend 机器）。

## 新增的未迁移示例（供端到端测试）

源仓新放了两个**尚未迁移**的叶子算子（无 in-tree 依赖，最易跑通），可用来验证规范化后的
asc 布局与整条迁移链路：

| 算子 | 源头文件 | 语义 | 形态 |
|---|---|---|---|
| `median3` | `__algorithm/median3.h` | 三个值取中位数 | 3 输入 → 1 输出 |
| `saturate_sub` | `__numeric/saturate_sub.h` | 饱和减：`a>b ? a-b : 0` | 2 输入 → 1 输出 |

各自带平行的 `test/libcudacxx/std/.../<op>.pass.cpp` 语义基准。迁移后应分别落到
`repos/accl/asc-stl/include/asc/std/__algorithm/median3.h` 与
`…/__numeric/saturate_sub.h`，并生成对应的 host / kernel 测试。
