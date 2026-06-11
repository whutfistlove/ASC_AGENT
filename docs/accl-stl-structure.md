# accl / libasccxx 目录结构

---

## 实现现状 vs 目标布局（务必先读）

本文件描述的是 **目标布局**（`std/` 提升为与 `asc/` 平级、`__cccl → common/__asc/` 移出 std 子树、
对外 `<std/*>`）。但**当前代码实现的仍是另一套布局**：

| 维度 | 本文目标布局 | 代码当前实现（`config/settings.yaml`） |
|---|---|---|
| 目标前缀 | `libasccxx/include/std/...` | `asc-stl/include/asc/std/...`（`mapping.target_repo_prefix`） |
| 底层配置目录 | `common/__asc/` | `asc/std/__asc/`（`mapping.segment_substitutions: __cccl→__asc`） |

> 之所以没有在本轮直接把整棵树切到目标布局：(1) 这是有产品影响、且会重命名全部已迁移头/guard
> 的高风险动作；(2) 本结构文档尚未提交、仍可能调整。**先把布局拍板再切**更稳妥。

好消息是：路径/命名映射已**完全配置化**（`mapping.target_repo_prefix` / `segment_substitutions`
驱动 `core/path_mapper.py`；迁移策略走 `config.migration_policy`）。因此真正切换布局是一次
**配置编辑**（改 `target_repo_prefix` 与段替换规则）而非改代码——拍板后即可平滑迁移并跑全仓回归。

---

## 0. 对照基线（ibcudacxx 仓）

命名约定：

| 维度 | libcudacxx | libasccxx |
|---|---|---|
| 顶层 monorepo | `cccl/` | `accl/` |
| 标准库（本库） | `libcudacxx/` | `libasccxx/` |
| 标准库命名空间 / 路径 | `cuda::std` / `<cuda/std/*>` | `asc::std` / `<std/*>` |
| 扩展命名空间 / 路径 | `cuda::` / `<cuda/*>` | `asc::` / `<asc/*>` |
| 共同引用 / 共享底层（★新增） | （并入 `cuda/std/__cccl/`） | `common/` / `<common/*>`（与 `std/`、`asc/` **平级**） |
| 底层配置目录 | `cuda/std/__cccl/` | `common/__asc/`（⟵ 原 `asc/std/__asc/`，★移出 std 子树） |
| 厂商 target 派发 | `nv/` | `ascend/` |
| device 注解 | `__host__ / __device__` | `__host__ / __aicore__` |

---

## 1. 目录树（实测基准 ↔ 映射结果，逐级对应）


> 计数已按实测核对：`cuda/std/__*` = **42** 个 facility 目录（+ `__cccl` + `detail`），`cuda/__*` 扩展 = **36** 个目录。

### 1.A　libcudacxx（对照基准）

```text
libcudacxx/                                   # → libasccxx/        NVIDIA 版 C++ 标准库（纯头文件）
├── CMakeLists.txt                            # → 同名             库构建入口
├── LICENSE.TXT                               # → 同名             Apache-2.0 WITH LLVM-exception
├── benchmarks/                               # → 同名             性能基准工程（独立 CMake）
│   ├── CMakeLists.txt                        # → 同名
│   └── bench/                                # → 同名             基准用例，按算子一目录（reduce/sort/transform/find/… 共约 60 个）
├── cmake/                                     # → 同名             构建辅助脚本（LLVM 配置 / 目标三元组 / 头文件测试规则）
├── codegen/                                   # → 同名             代码生成器（原子/指令封装头）
│   ├── codegen.cpp                           # → 同名             生成器主程序
│   ├── *.py                                  # → 同名             生成脚本（add_ptx_instruction / cccl_paths / prologue_epilogue）
│   └── generators/                           # → 同名             指令族模板（cas/exchange/fence/fetch_ops/ld_st/…）
├── test/                                      # → 同名             测试总根（lit 驱动）
│   ├── libcudacxx/                           # → test/asccxx/     本库主测试树（lit.cfg + force_include.h）
│   │   ├── std/                              # → test/asccxx/std/         标准设施一致性测试
│   │   ├── cuda/                             # → test/asccxx/asc/         扩展层专属测试
│   │   ├── libcxx/                           # → test/asccxx/libcxx/      fork 实现自测
│   │   └── heterogeneous/                    # → test/asccxx/heterogeneous/  host↔device 跨端测试
│   ├── nvtarget/                             # → test/ascend_target/   target 派发宏测试
│   │   ├── dialect/                          # → 同名             方言/编译期分支
│   │   ├── arch_specific/                    # → 同名             特定架构判定
│   │   └── family_specific/                  # → 同名             特定芯片族判定
│   ├── atomic_codegen/                       # → 同名             原子生成代码汇编落地校验
│   ├── simd_codegen/                         # → 同名             SIMD 生成代码校验
│   │   └── load_store/                       # → 同名             访存指令样例
│   ├── cmake/                                 # → 同名             测试工程 CMake 辅助
│   ├── maintenance/                          # → 同名             维护性巡检脚本
│   ├── support/                              # → 同名             测试公共夹具（Counter/MoveOnly/allocators…）
│   │   ├── random_utilities/                 # → 同名
│   │   ├── test.workarounds/                 # → 同名
│   │   └── type_classification/              # → 同名
│   └── utils/                                 # → 同名             测试运行器/工具
│       ├── libcudacxx/                       # → test/utils/libasccxx/
│       └── nvidia/                           # → test/utils/ascend/
└── include/                                   # → 同名             对外公开头文件根
    ├── cuda/                                  # → asc/             命名空间根 cuda::（★accl 侧仅扩展层；std/ 提升为与 asc/ 平级）
    │   │
    │   ├── std/                              # → std/（★提升为与 asc/ 平级）         cuda::std：符合 ISO C++ 的标准库（host + device）
    │   │   │
    │   │   ├── __cccl/                       # → common/__asc/           跨树底层配置宏（★改名，移出 std 子树到 common/）
    │   │   │
    │   │   ├── __<facility>/  ×42            # → 同名 ×42         标准设施实现细节（私有头），目录名保留：
    │   │   │                                 #   __algorithm __atomic __barrier __bit __charconv __chrono __cmath __complex
    │   │   │                                 #   __concepts __cstddef __cstdlib __cstring __exception __execution __expected
    │   │   │                                 #   __floating_point __format __functional __fwd __host_stdlib __internal __iterator
    │   │   │                                 #   __latch __limits __linalg __mdspan __memory __new __numeric __optional __pstl
    │   │   │                                 #   __random __ranges __semaphore __simd __string __system_error __thread
    │   │   │                                 #   __tuple_dir __type_traits __utility __variant
    │   │   │   ├── __atomic/{api,functions,platform,types,wait}/  # → 同名   原子实现分层
    │   │   │   ├── __format/formatters/      # → 同名             formatter 特化
    │   │   │   ├── __pstl/cuda/              # → __pstl/asc/      并行算法后端（★改名）
    │   │   │   └── __simd/specializations/   # → 同名             SIMD 类型特化
    │   │   │
    │   │   ├── detail/                       # → 同名             实现层配置目录
    │   │   │   └── __config                  # → 同名             实现层总配置入口（单文件）
    │   │   │
    │   │   ├── <umbrella>                    # → 同名             无扩展名公共伞头：array atomic chrono cmath complex memory
    │   │   │                                 #   ranges tuple type_traits utility variant version …
    │   │   └── algorithm.<op>.h              # → 同名             单算子细分伞头（clamp/copy/find/sort/…）
    │   │
    │   ├── __<facility>/  ×通用              # → 同名             扩展层 device 增强（28 个，目录名保留）：
    │   │                                     #   __algorithm __annotated_ptr __argument __atomic __barrier __bit __cmath
    │   │                                     #   __complex __container __device __event __execution __functional __fwd
    │   │                                     #   __internal __iterator __latch __launch __mdspan __memcpy_async __memory
    │   │                                     #   __memory_pool __memory_resource __numeric __random __semaphore __stream __type_traits
    │   ├── __hierarchy/                      # → 同名             执行层级抽象（grid/block 层级）
    │   │   └── queries/                      # → 同名             层级维度查询
    │   ├── __utility/__basic_any/            # → 同名             类型擦除容器（唯一带子目录的 __utility）
    │   ├── __runtime/                        # → 同名             运行时层封装（→ CANN runtime）
    │   ├── __driver/                         # → 同名             驱动层接口（→ ACL/驱动）
    │   ├── __ptx/                            # → __npu_isa/       底层 ISA 指令封装（★改名）
    │   │   ├── instructions/generated/       # → 同名             指令封装代码生成产物
    │   │   └── pragmas/                      # → 同名
    │   ├── __tma/                            # → __mte/           异步内存搬运引擎（★改名）
    │   ├── __warp/                           # → __vector/        SIMD 通道协作（★改名）
    │   ├── __nvtx/                           # → __msprof/        性能打点标注（★改名）
    │   │
    │   ├── <umbrella>                        # → 同名             扩展层公共伞头：algorithm atomic memory stream hierarchy
    │   │                                     #   launch pipeline devices access_property version …
    │   ├── execution.<sub>.h                 # → 同名             执行策略细分伞头（policy/require/tune/…）
    │   ├── ptx                               # → isa              （★改名，底层 ISA 公共伞头）
    │   ├── tma                               # → mte              （★改名）
    │   └── warp                              # → vector           （★改名）
    │
    └── nv/                                    # → ascend/          厂商 target 派发（平行于 cuda/；内容均为头文件）
        ├── target                            # → 同名             文件：派发标签头 __host__/__device__、NV_IF_TARGET
        └── detail/                            # → 同名             派发内部实现（仅下列两个头文件）
            ├── __preprocessor                # → 同名             文件：预处理元编程工具宏
            └── __target_macros               # → 同名             文件：目标平台判定宏
```

### 1.B　libasccxx（accl 映射结果）

```text
asc_stl/                                         # 顶层 monorepo（对标 cccl）
└── libasccxx/                                # ★ 对标 libcudacxx：Ascend 版 C++ 标准库（纯头文件）
    ├── CMakeLists.txt                        # ⟵ libcudacxx/CMakeLists.txt   库构建入口（纯头库的安装/测试目标）
    ├── LICENSE.TXT                           # ⟵ libcudacxx/LICENSE.TXT      许可证（Apache-2.0 WITH LLVM-exception）
    ├── benchmarks/                           # ⟵ benchmarks/   性能基准工程（独立 CMake）
    │   ├── CMakeLists.txt                    # ⟵ benchmarks/CMakeLists.txt   基准构建入口
    │   └── bench/                            # ⟵ benchmarks/bench/   基准用例，按算子一目录（reduce/sort/transform/find/…）
    ├── cmake/                                # ⟵ cmake/   构建辅助脚本（LLVM 配置、目标三元组探测、公/私头文件测试规则）
    ├── codegen/                              # ⟵ codegen/   代码生成器：从模板批量生成原子/指令封装头
    │   ├── codegen.cpp                       # ⟵ codegen/codegen.cpp        生成器主程序
    │   ├── *.py                              # ⟵ codegen/*.py               生成脚本（指令登记、路径、prologue/epilogue 生成）
    │   └── generators/                       # ⟵ codegen/generators/   各指令族模板（cas/exchange/fence/fetch_ops/ld_st…）
    ├── test/                                 # ⟵ test/   测试总根（lit 驱动），含 CREDITS/NOTES/TODO 等说明文件
    │   ├── asccxx/                           # ⟵ test/libcudacxx/   本库主测试树（lit.cfg + force_include.h 在此）
    │   │   ├── std/                          # ⟵ test/libcudacxx/std/    标准设施一致性测试（对标 ISO C++）
    │   │   ├── asc/                          # ⟵ test/libcudacxx/cuda/   扩展层（asc::）专属测试
    │   │   ├── libcxx/                       # ⟵ test/libcudacxx/libcxx/ fork 实现自测（私有头/实现细节）
    │   │   └── heterogeneous/                # ⟵ test/libcudacxx/heterogeneous/   host↔device 跨端一致性测试
    │   ├── ascend_target/                    # ⟵ test/nvtarget/   target 派发宏测试（对标 ascend/target）
    │   │   ├── dialect/                      # ⟵ test/nvtarget/dialect/         C++ 方言/编译期分支
    │   │   ├── arch_specific/                # ⟵ test/nvtarget/arch_specific/   特定架构判定
    │   │   └── family_specific/              # ⟵ test/nvtarget/family_specific/ 特定芯片族判定
    │   ├── atomic_codegen/                   # ⟵ test/atomic_codegen/   原子操作生成代码的汇编落地校验
    │   ├── simd_codegen/                     # ⟵ test/simd_codegen/   SIMD 生成代码校验
    │   │   └── load_store/                   # ⟵ test/simd_codegen/load_store/   访存指令样例
    │   ├── cmake/                            # ⟵ test/cmake/   测试工程的 CMake 辅助
    │   ├── maintenance/                      # ⟵ test/maintenance/   维护性脚本（头文件自包含/格式等巡检）
    │   ├── support/                          # ⟵ test/support/   测试公共头（Counter/MoveOnly/allocators 等夹具）
    │   │   ├── random_utilities/             # ⟵ test/support/random_utilities/   随机数测试辅助
    │   │   ├── test.workarounds/             # ⟵ test/support/test.workarounds/    编译器缺陷规避
    │   │   └── type_classification/          # ⟵ test/support/type_classification/ 类型分类夹具
    │   └── utils/                            # ⟵ test/utils/   测试运行器/工具
    │       ├── libasccxx/                    # ⟵ test/utils/libcudacxx/   本库 lit 工具
    │       └── ascend/                       # ⟵ test/utils/nvidia/       厂商专属测试工具
    └── include/                              # ⟵ include/   对外公开头文件根；★三者平级：std/（标准库）、asc/（扩展）、common/（共同引用）
        ├── std/                              # ⟵ cuda/std/   asc::std：符合 ISO C++ 的标准库，可在 host 与 NPU 上编译
        │   │                                 #   ★由 cuda/std/ 提升为 include/ 下与 asc/ 平级（不再嵌套在 asc/ 内）
        │   ├── __<facility>/  ×42            # ⟵ cuda/std/__<facility>/  ×42   各标准设施的实现细节（私有头），目录名 1:1 保留
        │   │                                 #   __algorithm __atomic __barrier __bit __charconv __chrono __cmath __complex
        │   │                                 #   __concepts __cstddef __cstdlib __cstring __exception __execution __expected
        │   │                                 #   __floating_point __format __functional __fwd __host_stdlib __internal __iterator
        │   │                                 #   __latch __limits __linalg __mdspan __memory __new __numeric __optional __pstl
        │   │                                 #   __random __ranges __semaphore __simd __string __system_error __thread
        │   │                                 #   __tuple_dir __type_traits __utility __variant   （全量见 §2，无一改名）
        │   │   ├── __atomic/{api,functions,platform,types,wait}/   # ⟵ 同路径   原子实现按 API/平台/类型/wait 分层
        │   │   ├── __format/formatters/      # ⟵ cuda/std/__format/formatters/   各类型的 formatter 特化
        │   │   ├── __pstl/asc/               # ⟵ cuda/std/__pstl/cuda/   并行算法后端目录（cuda→asc，★随命名空间改名）
        │   │   └── __simd/specializations/   # ⟵ cuda/std/__simd/specializations/   SIMD 类型特化
        │   │
        │   ├── detail/                       # ⟵ cuda/std/detail/   fork 自 libc++ 的实现层配置目录（std 私有）
        │   │   └── __config                  # ⟵ cuda/std/detail/__config   实现层总配置入口（单文件）；仅向下 #include <common/__asc/...>
        │   │
        │   ├── <umbrella>                    # ⟵ cuda/std/<umbrella>   无扩展名公共伞头，全部沿用：
        │   │                                 #   array atomic chrono cmath complex memory ranges tuple
        │   │                                 #   type_traits utility variant version …（对应上面的 __<facility>/）
        │   └── algorithm.<op>.h              # ⟵ cuda/std/algorithm.<op>.h   单算子细分伞头（clamp/copy/find/sort/…）
        │
        ├── asc/                              # ⟵ cuda/   命名空间根 asc::（★仅扩展层；std/ 子树已提升为与 asc/ 平级，见上）
        │   ├── __<facility>/  ×通用          # ⟵ cuda/__<facility>/   扩展层「与同名标准设施的 device 增强」，目录名沿用：
        │   │                                 #   __algorithm/ __annotated_ptr/ __argument/ __atomic/ __barrier/ __bit/
        │   │                                 #   __cmath/ __complex/ __container/ __device/ __event/ __execution/
        │   │                                 #   __functional/ __fwd/ __internal/ __iterator/ __latch/ __launch/
        │   │                                 #   __mdspan/ __memcpy_async/ __memory/ __memory_pool/ __memory_resource/
        │   │                                 #   __numeric/ __random/ __semaphore/ __stream/ __type_traits/
        │   ├── __hierarchy/                  # ⟵ cuda/__hierarchy/   执行层级抽象（grid/block → block / AI Core 层级）
        │   │   └── queries/                  # ⟵ cuda/__hierarchy/queries/   层级维度查询
        │   ├── __utility/__basic_any/        # ⟵ cuda/__utility/__basic_any/   类型擦除容器（扩展层唯一带子目录的 __utility）
        │   ├── __runtime/                    # ⟵ cuda/__runtime/   运行时层封装（语义指向 CANN runtime），名称保留
        │   ├── __driver/                     # ⟵ cuda/__driver/    驱动层接口（语义指向 ACL/驱动），名称保留
        │   ├── __npu_isa/                    # ⟵ cuda/__ptx/       底层 ISA 指令封装（PTX → AI Core 指令），★改名
        │   │   ├── instructions/generated/   # ⟵ cuda/__ptx/instructions/generated/   指令封装代码生成产物
        │   │   └── pragmas/                  # ⟵ cuda/__ptx/pragmas/
        │   ├── __mte/                        # ⟵ cuda/__tma/       异步内存搬运引擎（TMA → Memory Transfer Engine），★改名
        │   ├── __vector/                     # ⟵ cuda/__warp/      SIMD 通道协作（warp → AI Core 向量单元），★改名
        │   ├── __msprof/                     # ⟵ cuda/__nvtx/      性能打点标注（NVTX → MindStudio profiling），★改名
        │   │
        │   ├── <umbrella>                    # ⟵ cuda/<umbrella>   扩展层公共伞头，沿用：algorithm atomic memory stream
        │   │                                 #   hierarchy launch pipeline devices access_property version …
        │   ├── execution.<sub>.h             # ⟵ cuda/execution.<sub>.h   执行策略细分伞头（policy/require/tune/…）
        │   ├── isa                           # ⟵ cuda/ptx    ★改名（底层 ISA 公共伞头）
        │   ├── mte                           # ⟵ cuda/tma    ★改名
        │   └── vector                        # ⟵ cuda/warp   ★改名
        │
        ├── common/                           # ★新增：std 与 asc 的「共同引用」（最底层叶子，被 std/、asc/ 引用，不反向依赖二者）
        │   └── __asc/                        # ⟵ cuda/std/__cccl/（★移出 std 子树，下沉至此）  跨整棵树共享的底层配置宏
        │                                     #   架构/编译器/可见性/方言判定 等；内含头文件全量见 §3
        │
        └── ascend/                           # ⟵ nv/   厂商 target 派发（与 std/、asc/、common/ 平级；内容均为头文件，非目录）
            ├── target                        # ⟵ nv/target            （文件：派发标签头 __host__/__aicore__、ASC_IF_TARGET 等）
            └── detail/                       # ⟵ nv/detail/   派发设施的内部实现（仅含下列两个头文件）
                ├── __preprocessor            # ⟵ nv/detail/__preprocessor   （文件：预处理元编程工具宏）
                └── __target_macros           # ⟵ nv/detail/__target_macros  （文件：目标平台判定宏）
```

---

## 2. 顶层与 include 目录对照表

| libcudacxx | libasccxx | 说明 |
|---|---|---|
| `cccl/` | `asc_stl/` | 顶层 monorepo |
| `libcudacxx/` | `libasccxx/` | 本库（C++ 标准库，纯头文件） |
| `include/cuda/` | `include/asc/` | 命名空间根（★仅扩展层；std/ 提升为平级） |
| `include/cuda/std/` | `include/std/` | `asc::std`，符合 ISO C++（★与 asc/ 平级，不再嵌套） |
| `include/cuda/std/__cccl/` | `include/common/__asc/` | 跨树底层配置宏（★移出 std 子树，下沉至 common/） |
| —（cccl 无独立 common） | `include/common/` | ★新增：std 与 asc 的共同引用（最底层叶子，不反向依赖） |
| `include/cuda/std/detail/__config` | `include/std/detail/__config` | fork 实现配置（std 私有，仅向下依赖 common/） |
| `include/cuda/std/__<facility>/` ×42 | `include/std/__<facility>/` ×42 | 标准库实现细节，原名保留 |
| `include/cuda/__<facility>/` ×36 | `include/asc/__<facility>/` ×36 | 扩展实现（部分改名，见 §3） |
| `include/nv/` | `include/ascend/` | 厂商 target 派发（目录，与 std/、asc/、common/ 平级） |
| `include/nv/target` | `include/ascend/target` | host/device 派发标签（**文件**） |
| `include/nv/detail/__preprocessor` | `include/ascend/detail/__preprocessor` | 预处理工具宏（**文件**） |
| `include/nv/detail/__target_macros` | `include/ascend/detail/__target_macros` | 目标平台宏（**文件**） |
| `test/libcudacxx/` | `test/asccxx/` | lit 测试树 |
| `test/nvtarget/` | `test/ascend_target/` | target 宏测试 |
| `test/utils/nvidia/` | `test/utils/ascend/` | 厂商测试工具 |
| `benchmarks/  cmake/  codegen/` | 同名保留 | 仓级设施 |

---

## 3. NVIDIA 专属设施 → Ascend 对位改名表

> 除下表外，`std/__*`（42）与标准库伞头全部保留原名，仅 `asc/` 扩展层与 `ascend/` 厂商层涉及改名。

| libcudacxx | libasccxx | 原因 |
|---|---|---|
| `cuda/std/__cccl/` | `common/__asc/` | 跨树底层配置宏目录（★移出 std 子树，下沉至与 `std/`、`asc/` 平级的 `common/`） |
| `nv/` `nv/target` | `ascend/` `ascend/target` | 厂商派发：`__host__/__device__` → `__host__/__aicore__` |
| `cuda/__ptx/` · `cuda/ptx` | `asc/__npu_isa/` · `asc/isa` | PTX 是 NV ISA → AI Core 底层指令封装 |
| `cuda/__tma/` · `cuda/tma` | `asc/__mte/` · `asc/mte` | Tensor Memory Accelerator → Memory Transfer Engine |
| `cuda/__warp/` · `cuda/warp` | `asc/__vector/` · `asc/vector` | warp（SIMT 32 lane）→ AI Core 向量单元 |
| `cuda/__nvtx/` | `asc/__msprof/` | NVTX 性能标注 → MindStudio profiling |
| `cuda/__driver/` | `asc/__driver/`（语义指向 ACL/驱动） | 驱动层接口，名称保留 |
| `cuda/__runtime/` | `asc/__runtime/`（语义指向 CANN runtime） | 运行时层，名称保留 |

`common/__asc/`（⟵ `cuda/std/__cccl/`）内配置头同步改名，其余保留：

| libcudacxx `__cccl/*` | libasccxx `__asc/*` |
|---|---|
| `cuda_capabilities.h` | `npu_capabilities.h` |
| `cuda_toolkit.h` | `cann_toolkit.h` |
| `ptx_isa.h` | `npu_isa.h` |
| `architecture.h` `compiler.h` `visibility.h` `dialect.h` `prologue.h` `epilogue.h` `diagnostic.h` `attributes.h` `builtin.h` `assert.h` `deprecated.h` `exceptions.h` `execution_space.h` `extended_data_types.h` `host_std_lib.h` `is_non_narrowing_convertible.h` `os.h` `preprocessor.h` `rtti.h` `sequence_access.h` `system_header.h` `unreachable.h` `version.h` | 原样保留 |

---

## 4. accl monorepo 顶层结构（与 libasccxx 同级的目录）

> 前三节只覆盖 `libcudacxx → libasccxx` 这一个库。但 `cccl/` 是一个 **monorepo**，`libcudacxx/` 只是其中一个子库；本节给出 `cccl/` 顶层（与 `libcudacxx/` **平级**）的全部目录及其 `accl/` 映射。
> 命名沿用既有规则：**含 `cuda`/`nv`/`cccl`/`ptx` 等 NVIDIA 品牌词的目录改名（★），其余保留原名**。库名是中性品牌（`cub`/`thrust`）的按"其余保留原名"处理；带 ★ 的为建议命名，可按团队约定调整。

### 4.A　cccl 顶层（对照基准）

```text
cccl/                                          # → accl/        CUDA Core Compute Libraries（monorepo 根）
├── libcudacxx/                                # → libasccxx/   C++ 标准库（纯头）——本文 §1 已逐级详述
├── cub/                                       # → cub/         device/block/warp 级并行原语（纯头，CUDA UnBound；名称中性，保留）
├── thrust/                                    # → thrust/      高层并行算法库（纯头，类 STL；名称中性，保留）
├── cudax/                                     # → ascx/        ★ CUDA Experimental：实验特性孵化区（纯头，API 不稳定）
├── c/                                         # → c/           CCCL C API：C 语言 ABI 封装（parallel / parallel.v2 / experimental-stf）
├── python/                                    # → python/      Python 包根；包目录 cuda_cccl → asc_accl（见 §4.D）
├── examples/                                  # → 同名         各库使用示例（basic / ccclrt / cudax / cudax_stf / …）
├── test/                                      # → 同名         ★仓级集成/冒烟测试（≠ libcudacxx/test 库内单测）
│   ├── cmake/test_export/                     # → 同名         CMake find_package/导出目标的下游消费验证
│   ├── cuda_smoke/                            # → asc_smoke/   CUDA runtime 冒烟（cuda_runtime_smoke.cu → asc_runtime_smoke.cu）
│   └── stdpar/                                # → 同名         C++ stdpar（std::execution::par）集成测试
├── benchmarks/                                # → 同名         仓级基准脚本/注册（区别于各库内部的 benchmarks/）
│   ├── cmake/                                 # → 同名         CCCLBenchmarkRegistry.cmake → ACCLBenchmarkRegistry.cmake
│   └── scripts/                               # → 同名         run/compare/analyze/search 等 Python 脚本
├── nvbench_helper/                            # → ascbench_helper/   ★ nvbench 基准框架接入层（device_side_benchmark / look_back_helper）
├── nvrtcc/                                    # → ascrtcc/     ★ NVRTC 运行时编译测试工具（内部工具，语义对位 CANN/NPU RTC）
├── c2h/                                       # → 同名         catch2 测试辅助（生成器/runner，名称中性）
├── ci/                                        # → 同名         CI 构建脚本：build_libcudacxx.sh → build_libasccxx.sh、build_cudax.sh → build_ascx.sh …
├── cmake/                                     # → 同名         仓级 CMake 模块；CCCL* 前缀 → ACCL*（CCCLAddExecutable.cmake → ACCLAddExecutable.cmake …）
├── lib/                                       # → 同名         各库安装/导出树占位：cccl/ cub/ cudax/ libcudacxx/ thrust/
├── docs/                                      # → 同名         Sphinx 文档：libcudacxx→libasccxx、cudax→ascx、cccl→accl，cub/thrust 保留
├── CMakeLists.txt  CMakePresets.json          # → 同名         monorepo 顶层构建入口与预设
├── README.md  LICENSE  CONTRIBUTING.md        # → 同名         说明/许可证/贡献指南（CODE_OF_CONDUCT / SECURITY / CITATION 同）
├── pyproject.toml  cccl-version.json          # → 同名         Python 工程元数据与版本号（cccl-version.json 内容随版本号改）
└── AGENTS.md  CLAUDE.md  ci-overview.md        # → 同名         智能体/CI 说明文件（保留）
```

### 4.B　accl 顶层（映射结果）

```text
accl/                                          # ⟵ cccl/        Ascend Core Compute Libraries（monorepo 根）
├── libasccxx/                                 # ⟵ libcudacxx/  C++ 标准库（纯头）——§1 已详述
├── cub/                                       # ⟵ cub/         device/block/warp 级并行原语（名称保留）
├── thrust/                                    # ⟵ thrust/      高层并行算法库（名称保留）
├── ascx/                                      # ⟵ cudax/       ★ Ascend Experimental：实验特性孵化区
├── c/                                         # ⟵ c/           ACCL C API：C 语言 ABI 封装
├── python/                                    # ⟵ python/      Python 包根（见 §4.D）
├── examples/                                  # ⟵ examples/    各库使用示例（acclrt / ascx / ascx_stf …，见 §4.C）
├── test/                                      # ⟵ test/        仓级集成/冒烟测试（cmake 导出 / asc_smoke / stdpar）
├── benchmarks/                                # ⟵ benchmarks/  仓级基准脚本/注册
├── ascbench_helper/                           # ⟵ nvbench_helper/   ★ 基准框架接入层
├── ascrtcc/                                   # ⟵ nvrtcc/      ★ 运行时编译测试工具（语义对位 CANN/NPU RTC）
├── c2h/                                       # ⟵ c2h/         catch2 测试辅助
├── ci/                                        # ⟵ ci/          CI 构建脚本（build_libasccxx.sh / build_ascx.sh …）
├── cmake/                                     # ⟵ cmake/       仓级 CMake 模块（ACCL* 前缀）
├── lib/                                       # ⟵ lib/         安装/导出树占位：accl/ cub/ ascx/ libasccxx/ thrust/
├── docs/                                      # ⟵ docs/        Sphinx 文档（libasccxx / ascx / accl …）
├── CMakeLists.txt  CMakePresets.json          # ⟵ 同名         顶层构建入口与预设
├── README.md  LICENSE  CONTRIBUTING.md        # ⟵ 同名
├── pyproject.toml  accl-version.json          # ⟵ pyproject.toml / cccl-version.json
└── AGENTS.md  CLAUDE.md  ci-overview.md        # ⟵ 同名
```

### 4.C　顶层目录对照表

| cccl（基准） | accl（映射） | 性质 | 说明 |
|---|---|---|---|
| `libcudacxx/` | `libasccxx/` | 库（纯头） | C++ 标准库 + 扩展（本文 §1～§3） |
| `cub/` | `cub/` | 库（纯头） | device/block/warp 并行原语；名称中性，保留 |
| `thrust/` | `thrust/` | 库（纯头） | 高层 STL 风格并行算法；名称中性，保留 |
| `cudax/` | `ascx/` ★ | 库（纯头） | 实验特性孵化区（API 不稳定） |
| `c/` | `c/` | 库（C API） | C 语言 ABI 封装：`parallel` / `parallel.v2`(HostJIT) / `experimental/stf` |
| `python/cuda_cccl/` | `python/asc_accl/` ★ | Python 包 | 见 §4.D |
| `examples/` | `examples/` | 示例 | 子目录见下 |
| `examples/ccclrt/` | `examples/acclrt/` ★ | 示例 | CCCL runtime 示例 |
| `examples/cudax/` `examples/cudax_stf/` | `examples/ascx/` `examples/ascx_stf/` ★ | 示例 | cudax 随库改名 |
| `examples/basic/` `examples/thrust_flexible_device_system/` | 同名 | 示例 | 名称中性，保留 |
| `test/` | `test/` | 仓级测试 | 集成/冒烟测试，**区别于** `libcudacxx/test/`（§1 库内单测） |
| `test/cmake/test_export/` | 同名 | 仓级测试 | CMake `find_package`/导出目标下游消费验证 |
| `test/cuda_smoke/` | `test/asc_smoke/` ★ | 仓级测试 | runtime 冒烟（`cuda_runtime_smoke.cu` → `asc_runtime_smoke.cu`） |
| `test/stdpar/` | `test/stdpar/` | 仓级测试 | C++ stdpar 集成测试；名称中性，保留 |
| `benchmarks/` | `benchmarks/` | 仓级设施 | 仓级基准脚本/注册（≠ 各库内 `benchmarks/`） |
| `nvbench_helper/` | `ascbench_helper/` ★ | 工具 | 基准框架接入层 |
| `nvrtcc/` | `ascrtcc/` ★ | 工具（内部） | 运行时编译测试工具 |
| `c2h/` | `c2h/` | 工具 | catch2 测试辅助；名称中性，保留 |
| `ci/` | `ci/` | 仓级设施 | 构建脚本随库名改（见 §4.B） |
| `cmake/` | `cmake/` | 仓级设施 | `CCCL*` 模块前缀 → `ACCL*` |
| `lib/` | `lib/` | 仓级设施 | 安装/导出树占位，子目录随各库改名 |
| `docs/` | `docs/` | 文档 | 子目录随各库改名（`cub`/`thrust` 保留） |
| 顶层 `*.md` / `*.txt` / `*.json` / `*.toml` | 同名 | 配置/文档 | `cccl-version.json → accl-version.json` |

### 4.D　Python 包映射（`python/cuda_cccl` → `python/asc_accl`）

> 规则：`cuda → asc`、`cccl → accl`（与命名空间一致）；PyPI 包 `cuda-cccl → asc-accl`，导入 `import cuda.compute` → `import asc.compute`。

| cccl | accl | 说明 |
|---|---|---|
| `python/cuda_cccl/` | `python/asc_accl/` | Python 包根（`pyproject.toml` / `tests` / `benchmarks` / `merge_*_wheels.py`） |
| `cuda/cccl/` | `asc/accl/` | 基础设施：`headers`（随包分发的头文件）、`parallel`、版本工具 |
| `cuda/compute/` | `asc/compute/` | device 级并行算法（reduce/scan/sort/…）与 iterator 的绑定（Cython `.pyx`/`.pxi`） |
| `cuda/coop/` | `asc/coop/` | block/warp 级协作原语（`_experimental`），供自定义 kernel 调用 |
| PyPI `cuda-cccl` | `asc-accl` | 安装包名；`cuda.compute` / `cuda.coop` → `asc.compute` / `asc.coop` |

---

## 5. `std`/`asc`/`common` 三者平级与 `common/` 设计（本次新增）


### 5.1 问题：std 子树 ↔ cuda 外层的内外层交叉引用

cccl 把 `std/` 嵌套在 `cuda/` 内，二者还共用埋在 `std/` 子树深处的配置 `cuda/std/__cccl/`：

```text
include/
└── cuda/                 # 命名空间根 cuda::（扩展层）
    └── std/              # cuda::std（嵌套）
        └── __cccl/       # 号称「跨整棵树共享」的底层配置宏
```

矛盾在于：`cuda/std/__cccl/` 名义上**跨整棵树共享**，物理上却在 `std/` 私有深处；而外层 `cuda/` 扩展头又要反向 `#include <cuda/std/__cccl/...>`。于是形成「外层 `cuda/` ↔ 内层 `std/`」的交叉引用——内层私有子目录被外层依赖，层次方向混乱。

### 5.2 拆平后的新问题

把 `std/` 与 `asc/` 提升为兄弟目录后，共享的 `__cccl/`（→ `__asc/`）失去中性归属：留在 `std/__asc/` 则 `asc/` 要横向伸进 `std/` 私有子树；放进 `asc/` 则 `std/` 反过来依赖 `asc/`。两条路都把交叉引用从「上下层」平移成「左右兄弟」，没根治。

### 5.3 方案：新增同级 `common/`，形成单向分层依赖

```text
依赖方向自上而下（上层 → 下层），不存在向上箭头：

   ┌──────────────────────────────────────────────┐
   │  asc/        namespace asc::（NPU 扩展）        │
   └───────────────┬─────────────────────┬─────────┘
                   │ 引用                │ 引用
                   ▼                     │
   ┌───────────────────────────┐         │
   │  std/   namespace asc::std │         │
   │         （ISO C++ 标准库） │         │
   └───────────────┬───────────┘         │
                   │ 引用                │ 引用
                   ▼                     ▼
   ┌──────────────────────────────────────────────┐
   │  common/    共享底层（配置宏 / 公共基础设施）  │
   │             不反向依赖 std/ 与 asc/            │
   └──────────────────────────────────────────────┘
```

- `asc/ → std/`：扩展层在标准设施上做 device 增强，本就依赖 `std/`。
- `asc/ → common/`、`std/ → common/`：二者都取用 `common/` 的配置与公共基础。
- `common/` 是叶子层（只被依赖、不回指）⇒ 依赖图无环，原 std↔cuda 内外层互引消失。


