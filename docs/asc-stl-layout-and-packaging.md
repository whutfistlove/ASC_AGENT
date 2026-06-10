# ASC-STL 目录规划与出包方案

> 面向 **CANN/asc-stl** 仓的前期决策文档，回答两件事：
> **(1) 头文件目录如何规划**（借鉴 CCCL/libcu++，敲定 asc-stl 的目录与命名）；
> **(2) 项目完成后如何出包**（run 包等格式的选型与流水线）。
>
> 依据：官方《ASC-STL 仓规划》方案、libcu++ 的 `std:: / cuda:: / cuda::std::` 谱系设计。

---

## 0. 结论速览

**目录规划**

- asc-stl 对标的是 **libcu++（libcudacxx）这一“CUDA 版 C++ 标准库”**，不是整个 cccl monorepo；
  因此 `include/` 直接放在仓根，无需额外的库名嵌套层级。
- 沿用 libcu++ 最核心的设计——**用“命名空间 = 头文件路径”的谱系来切分能力**：
  | libcu++ 谱系 | 头文件路径 | 作用域 | asc-stl 对应 |
  |---|---|---|---|
  | `std::` | `<*>`（host 编译器自带） | 仅 host | 不归我们管 |
  | `cuda::std::` | `<cuda/std/*>` | host + device | **`asc::std`**（标准库，对标 ISO C++） |
  | `cuda::` | `<cuda/*>` | host + device | **`asc::`**（NPU 额外扩展） |
  | `cuda::device::` | `<cuda/device/*>` | 仅 device | **`asc::device`**（仅 AI Core 的扩展，建议预留） |
- 推荐让 **路径前缀 == 命名空间前缀**（即 `include/asc/std/...` ↔ `asc::std`），这是 libcu++ 一直坚持的不变式，下游 `#include` 路径与符号能对上号。详见 [§1.3 方案 A/B 对比](#方案-a-vs-方案-binclude-std-还是-include-ascstd需团队拍板)。

**出包方式**

- asc-stl 是 **header-only**（CMake 里是 `INTERFACE` 库），所以“打包”本质是
  **摆放头文件 + 导出 CMake 包配置 + 带上 LICENSE/版本**，没有 ABI、不依赖目标架构。
- **主交付：`.run` 自解压安装包**（对齐 CANN 生态：toolkit / nnrt / kernels 全是 .run），
  内核是 **`cmake --install` 产物**，载荷可同时产出一份 **`tar.gz`**；
  并**导出 `find_package(asc-stl CONFIG)` 包配置**，覆盖源码集成路径。

---

# 1. 头文件目录规划

## 1.1 先看清楚源：CCCL 的目录结构

CCCL（CUDA C++ Core Libraries）是一个 **monorepo（单仓多库）**，把原来分散的三大库收进同一个仓：

```text
cccl/                              # 顶层 monorepo（Apache-2.0 WITH LLVM-exception）
├── libcudacxx/                    # ★ libcu++：CUDA 版 C++ 标准库（纯头文件库）——asc-stl 真正对标的就是它
│   ├── include/
│   │   ├── cuda/
│   │   │   ├── std/               # cuda::std::  —— 符合 ISO C++ 的实现，host+device 都能用
│   │   │   │   ├── __algorithm/   #   实现细节子目录：带 __ 前缀，按设施(facility)拆分
│   │   │   │   ├── __atomic/
│   │   │   │   ├── __type_traits/
│   │   │   │   ├── __utility/
│   │   │   │   ├── ...            #   几十个 __xxx/ 细分目录
│   │   │   │   ├── array  atomic  tuple  type_traits  span ...   # 无扩展名的“伞头”(public umbrella header)
│   │   │   │   └── detail/libcxx/ #   从 LLVM libc++ fork 来的实现（出处 + license 关键）
│   │   │   ├── __cccl/            # 跨库共享配置（编译器/架构/可见性/诊断 等基础宏）
│   │   │   ├── std/               # <cuda/std/...> 的入口转发
│   │   │   ├── atomic barrier pipeline annotated_ptr memory_resource ...  # cuda:: 扩展(host+device)
│   │   │   └── ...
│   │   └── nv/                    # nv/target：__host__ / __device__ 派发标签
│   ├── test/                      # 测试（lit 布局，<op>.pass.cpp）
│   ├── docs/  cmake/  examples/
├── cub/                           # CUB：block/warp/device 级并行原语（偏 device）
├── thrust/                        # Thrust：高层并行算法（host+device，类 STL 接口）
├── cudax/                         # 实验性加速扩展库
├── c/  python/                    # C / Python 绑定
├── docs/  cmake/  examples/  ci/  # 仓级公共设施
├── LICENSE                        # Apache-2.0 WITH LLVM-exception
└── README.md
```

**关键观察**：asc-stl 要对标的是 **libcudacxx 这一个库**（C++ 标准库部分），不是 cub/thrust。
所以 asc-stl 是“单库仓”，`include/` 应直接落在仓根，无需复制 cccl 的 monorepo 外层。

## 1.2 CCCL 的核心设计思想：用“命名空间谱系”切分能力

libcu++ 最重要的设计，是把能力按 **命名空间 + 头文件路径 + 可运行位置** 切成四条谱系：

| 谱系 | 头文件 | 含义 | 可运行位置 |
|---|---|---|---|
| `std::` | `<*>` | host 编译器自带的标准库，libcu++ 不替换、不干预 | **仅 host**（`--expt-relaxed-constexpr` 下 constexpr 可进 device） |
| `cuda::std::` | `<cuda/std/*>` | **符合标准**的 C++ 标准库设施实现 | **host + device** |
| `cuda::` | `<cuda/*>` | 对标准库的**符合性扩展**（标准里没有、但 CUDA 编程模型必需） | **host + device** |
| `cuda::device::` | `<cuda/device/*>` | 扩展中**只在 device 侧**有意义的部分 | **仅 device** |

这套切分值得照搬的原因：

1. **路径即承诺**：看 `#include` 路径就知道这段代码“符不符合标准、能不能在 device 跑”。
2. **命名空间即隔离**：`cuda::std::` 与 host 的 `std::` 互不打架，可共存。
3. **可演进**：扩展（`cuda::`）和标准实现（`cuda::std::`）分树存放，标准实现可对着 ISO 条款逐条对齐，扩展可自由发挥。

asc-stl 的规划正是这套思想的“Ascend 版”：`asc::std`（标准库）+ `asc::`（NPU 额外扩展），
两者都要**同时支持 SIMD 与 SIMT kernel**（Ascend 上 SIMD ≈ AI Core 向量单元 `__aicore__`，SIMT ≈ 线程/块 kernel 模型）。

## 1.3 asc-stl 目标目录设计（推荐）

综合 **官方规划**（仓名 `CANN/asc-stl`；一级目录 `include / examples / docs / cmake / test / third_party`；
`include` 下分 `std` 与 `asc`；命名空间 `asc::std` 与 `asc::`；Apache-2.0）+ **libcu++ 结构**，推荐如下：

```text
asc-stl/                           # 仓名 CANN/asc-stl（对标 libcudacxx 这一个库）
├── include/
│   └── asc/                       # ★ 命名空间根目录（让 路径前缀 == 命名空间前缀，见下方方案对比）
│       ├── std/                   # asc::std —— 对标 cuda/std：符合 ISO C++ 的标准库实现
│       │   │                      #   namespace asc::std；host + NPU kernel(SIMD/SIMT) 都能用
│       │   ├── __algorithm/       #   实现细节子目录（沿用 libcu++ 的 __xxx/ 拆分法）
│       │   ├── __numeric/
│       │   ├── __type_traits/
│       │   ├── __utility/
│       │   ├── __functional/
│       │   ├── __config           #   总配置头：命名空间宏 / _ASC_AICORE_FN / 编译器&平台探测
│       │   ├── algorithm numeric type_traits utility ...   # 无扩展名“伞头”（聚合 __xxx/ 的对外入口）
│       │   └── detail/            #   （可选）从 LLVM libc++ fork 的实现，保留出处与 license
│       ├── __asc/                 # 对标 __cccl：跨树共享的底层配置宏（编译器/架构/AICore 注解）
│       ├── device/               # asc::device —— 对标 cuda/device：仅 AI Core(device) 的扩展
│       │   │                      #   如 vector/cube 单元 intrinsic 包装、UB/GM 内存抽象、SIMD 原语
│       │   └── ...
│       ├── memory_resource barrier pipeline ...   # asc:: —— NPU 额外扩展（host + device）
│       └── ...
├── examples/                      # 可独立编译的最小使用样例（每个算子/特性一个）
├── test/                          # 测试树，与 include/ 平行；按执行单元分 host / device / kernel
│   └── asc/
│       ├── std/  device/  ...     # 子树与 include 对应；<op>.pass.cpp 风格
│       └── kernel/<op>_example/   # kernel 仿真用例（cannsim），见 §1.4
├── cmake/                         # 导出包配置(asc-stl-config.cmake)、工具链片段、find_package 支持
├── docs/                          # 设计/API/迁移文档
├── third_party/                   # 第三方依赖（libc++ 片段、googletest 等）+ 各自 license
├── scripts/                       # 构建/打包/代码风格/license-header hook 脚本
├── CMakeLists.txt                 # 顶层：INTERFACE 头文件库 + install/export 规则（见 §2）
├── version.txt                    # 版本号单一事实源（注入头 + 包名）
├── LICENSE  NOTICE                # Apache-2.0（若引用 libc++ 需附 LLVM-exception 与 NOTICE 出处）
└── README.md
```

各一级目录职责与“为什么这么放”：

| 目录 | 职责 | 对应 CCCL | 理由 |
|---|---|---|---|
| `include/asc/std/` | 符合 ISO C++ 的标准库实现，`asc::std` | `cuda/std/` | 标准实现独立成树，可对着标准条款逐条迁移/验证 |
| `include/asc/`（伞头层） | 对标准库的 NPU 扩展，`asc::` | `cuda/` | 扩展与标准实现分离，互不污染 |
| `include/asc/device/` | 仅 device(AI Core) 的扩展，`asc::device` | `cuda/device/` | 把“只能在 NPU 上跑”的设施显式隔出来，避免 host 误用 |
| `include/asc/__asc/`、`std/__config` | 底层配置与注解宏（编译器探测、`__aicore__` 注解、命名空间宏） | `__cccl/`、`std/__config` | 单一事实源，集中管理可移植性 |
| `examples/` | 可编译样例 | `examples/` | 既是文档也是回归用例 |
| `test/` | host/device/kernel 三类测试，平行于 include | `test/` | 与“host 编译 + kernel cannsim 仿真”链路一致 |
| `cmake/` | 包配置导出、工具链 | `cmake/` | 出包关键：让下游 `find_package(asc-stl)` 成立（见 §2） |
| `third_party/` | 第三方源 + license | （cccl 内嵌 libcxx fork） | Apache + LLVM-exception 合规的落点 |

### 方案 A vs 方案 B：`include/std` 还是 `include/asc/std`？（需团队拍板）

官方规划把 `std` 与 `asc` 列为 `include/` 下的**二级目录**。直译有两种落法：

- **方案 A（字面直译）**：`include/std/` 与 `include/asc/`，`#include <std/array>`、`<asc/...>`。
  - 缺点：命名空间是 `asc::std`，但路径是 `std/`（**不含 `asc/`**），**路径与命名空间前缀对不上**；
    且仓根 include 路径上出现裸 `std/`，阅读上易与系统 `<...>` 混淆。
- **方案 B（推荐，path == namespace）**：统一收进 `asc/` 根 → `include/asc/std/` 与 `include/asc/`，
  `#include <asc/std/array>`、`<asc/...>`。
  - 优点：**路径前缀 == 命名空间前缀**（`asc/std` ↔ `asc::std`，`asc/` ↔ `asc::`），
    正是 libcu++ 刻意维持的不变式（`<cuda/std/array>` ↔ `cuda::std`）；
    从 libcu++ 迁移过来的用户“肌肉记忆”可直接套用（`cuda` → `asc`）。
  - 与官方规划的关系：把“`include` 下分 `std` / `asc`”理解为“`include/asc/` 下分 `std`（标准）/ 扩展”，
    只多收一层 `asc/`，语义不变。

**建议采用方案 B**：它与“`asc::std` / `asc::`”的命名空间决策严丝合缝，也是 1:1 对标 CCCL 的最稳路径。
若坚持字面，则取方案 A 并在 README 注明“路径 `std/` 对应命名空间 `asc::std`”的非对称。

## 1.4 测试树：host / device / kernel 三分

测试按 §1.2 的“可运行位置”谱系切成三类，平行于 `include/`：

```text
test/asc/
├── std/__algorithm/clamp.pass.cpp        # host：普通 C++ 编译运行（用例名 host.clamp）
├── device/clamp_tests.cpp                # device：单算子在 device 注解下编译（用例名 device.clamp）
└── kernel/clamp_example/                 # kernel：完整 AscendC 算子 + cannsim 仿真（用例名 kernel.clamp.sim）
    ├── kernel.cpp  host.cpp  main.cpp  kernel_spec.json
    ├── cmake/npu_lib.cmake
    └── run_test.sh
```

- **host** 只依赖标准 C++，普通 Linux 即可跑——CI 友好、最快的语义回归。
- **device / kernel** 需要 CANN 工具链 + `cannsim`，验证 SIMD/SIMT kernel 真能编译与运行。
- 与 include 平行的子树让“头 ↔ 测试”一一对应，便于自动扫描。

---

# 2. 出包方式

## 2.1 前提判断：header-only 决定了打包形态

asc-stl 是**纯头文件库**——CMake 里是 `INTERFACE` 库，无 `.so/.a`、无 ABI、不绑架构。
因此“打包”不是“编译产物归档”，而是：

> **摆放头文件 + 导出 CMake 包配置 + 带上 LICENSE/NOTICE/版本 + （可选）examples/docs**。

两个推论：
1. 包**理论上 noarch**（同一份头文件 x86_64/aarch64 通用）；但为对齐 CANN 习惯，包名仍可带 arch 后缀。
2. 打包流水线非常稳定：`cmake --install` 出一个 staging 目录，剩下就是“封壳”。

## 2.2 候选格式横向对比

| 格式 | 优点 | 缺点 | 定位 |
|---|---|---|---|
| **`.run` 自解压包** | 对齐 CANN（toolkit/nnrt/kernels 全是 .run）；自带 install/uninstall/check/version/`set_env.sh`；单文件离线分发、可内嵌 examples+docs、可带 sha256 自校验 | 需维护自解压壳脚本 | **★ 主交付（面向 CANN 用户/集成）** |
| **CMake install + 包配置** | 下游 `find_package(asc-stl CONFIG)` 直接拿到 INTERFACE target；版本/依赖可传递 | 仅覆盖 CMake 工程 | **★ 内核（被其它库引用的首选）** |
| **`tar.gz` / `zip`** | 最朴素；可当 .run 的载荷；CMake `FetchContent`/`ExternalProject` 可直接拉 | 无安装/卸载/版本管理 | 轻量分发 + .run 中间产物 |
| `.deb` / `.rpm` | 进 apt/yum 源，系统级依赖管理 | 维护成本、与 CANN 安装路径需协调 | 二级（按需） |
| conda / vcpkg / Spack | 进 C++/科学计算生态 | 额外 recipe 维护 | 二级（按需） |

## 2.3 推荐方案：`.run` 为主壳，CMake install 为内核，tar.gz 为载荷

一条流水线同时产出三种制品，互为复用：

```text
版本号(version.txt) ─┐
                     ▼
   cmake --install --prefix stage/asc-stl   ← 内核：摆头文件 + 导出包配置 + LICENSE
                     │
                     ├──►  打 tar.gz：asc-stl_<ver>_noarch.tar.gz      （轻量分发 / 中间产物）
                     │
                     └──►  封 .run：payload = 上面的 tar，前置自解压壳脚本
                            ► Ascend-cann-asc-stl_<ver>_linux-<arch>.run   （主交付）
```

### (a) `.run` 包内布局

```text
Ascend-cann-asc-stl_<ver>_linux-<arch>.run
├── [自解压壳脚本]                 # makeself 风格：解析 --install/--uninstall/--check/--version/--quiet
└── [payload: asc-stl_<ver>.tar.gz]
    └── asc-stl/
        ├── include/asc/...        # 全部头文件
        ├── lib/cmake/asc-stl/     # asc-stl-config.cmake / *-version.cmake（find_package 用）
        ├── examples/  docs/
        ├── scripts/set_env.sh     # 导出 ASC_STL_HOME / 头文件搜索路径
        ├── version.info  sha256.txt
        └── LICENSE  NOTICE
```

`.run` 应支持的参数（对齐 CANN）：`--install`、`--install-path=<dir>`、`--uninstall`、`--check`、
`--version`、`--full`/`--quiet`、root 与非 root 安装。

### (b) CMake 安装/导出（内核）骨架

```cmake
# 顶层 CMakeLists.txt（节选）——把 INTERFACE 头文件库做成可 install/可 find_package
add_library(asc-stl INTERFACE)
add_library(asc-stl::asc-stl ALIAS asc-stl)
target_include_directories(asc-stl INTERFACE
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>)
target_compile_features(asc-stl INTERFACE cxx_std_17)

include(GNUInstallDirs CMakePackageConfigHelpers)
install(DIRECTORY include/ DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})
install(TARGETS asc-stl EXPORT asc-stl-targets)
install(EXPORT asc-stl-targets NAMESPACE asc-stl::
        DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/asc-stl)
write_basic_package_version_file(asc-stl-config-version.cmake
        VERSION ${PROJECT_VERSION} COMPATIBILITY SameMajorVersion)
# 配 asc-stl-config.cmake.in -> 安装后下游即可：
#   find_package(asc-stl CONFIG); target_link_libraries(app PRIVATE asc-stl::asc-stl)
```

下游三种集成路径都成立：`find_package(asc-stl CONFIG)`（装包后）、`FetchContent` / `add_subdirectory`（源码）。

### (c) 安装后落盘与环境

CANN 默认装在 `/usr/local/Ascend/...`。asc-stl 建议落在
`<ASCEND_HOME>/asc-stl/{include,lib/cmake,examples,docs}`，并由 `set_env.sh` 导出头文件搜索路径，
与其它 CANN 组件 `source set_env.sh` 的使用习惯一致。

### (d) 包命名规范（对齐 CANN）

CANN 现有包形如 `Ascend-cann-toolkit_8.0.RC1_linux-x86_64.run`。asc-stl 取
`Ascend-cann-asc-stl_<version>_linux-<arch>.run`。虽 noarch，但保留 `linux-<arch>` 后缀以对齐生态与发布系统。

## 2.4 License 与合规（务必随包带）

- 仓 license 为 **Apache-2.0**。但**标准库实现参考 LLVM 的 stl**——LLVM libc++ 是
  **Apache-2.0 *WITH* LLVM-exception**。**只要复用/fork 了 libc++ 代码**，对应文件就应保留
  **LLVM-exception** 头，并在 **`NOTICE`** 中标注 LLVM 出处。建议法务确认一次。
- 每个源文件带标准 Apache-2.0 头（建议用 pre-commit hook 自动补齐与校验）。
- `third_party/` 下每个第三方各自附原始 license。
- 包内根置 `LICENSE` + `NOTICE`，`.run` 安装时一并落盘。

## 2.5 版本与可重复构建

- `version.txt` 作为版本单一事实源：注入头文件（`asc/std/__config` 暴露 `ASC_STL_VERSION`）、注入包名、注入 `version.info`。
- `.run` 内置 `sha256.txt`，`--check` 校验完整性。
- 出包流水线纳入 CI：`tag → cmake --install → tar → makeself → 校验 → 发布`，可重复、可追溯。

---

# 3. 待团队确认的决策点

1. **include 布局**：方案 B（`include/asc/std`，path == namespace，**推荐**）还是方案 A（字面 `include/std`）。
2. **`asc::device` 子树**：是否现在就预留 `include/asc/device/`（对标 `cuda::device`，隔离“仅 AI Core”设施）。
3. **出包矩阵**：确认 **`.run` 为主 + CMake 包配置 + tar.gz**；是否追加 `.deb/.rpm` 或 conda（二级）。
4. **libc++ 合规**：是否复用 libc++ 代码 → 决定是否需要 **LLVM-exception + NOTICE**（建议法务过一遍）。

---

# 附录：CCCL ↔ asc-stl 速查表

| 维度 | CCCL / libcu++ | asc-stl（推荐） |
|---|---|---|
| 仓 | `cccl`（monorepo） | `CANN/asc-stl`（单库仓） |
| 标准库命名空间 / 路径 | `cuda::std` / `<cuda/std/*>` | `asc::std` / `<asc/std/*>` |
| 扩展命名空间 / 路径 | `cuda::` / `<cuda/*>` | `asc::` / `<asc/*>` |
| 仅 device 扩展 | `cuda::device` / `<cuda/device/*>` | `asc::device` / `<asc/device/*>` |
| 底层配置目录 | `__cccl/`、`std/__config` | `__asc/`、`asc/std/__config` |
| 实现细节子目录 | `cuda/std/__algorithm/ ...` | `asc/std/__algorithm/ ...` |
| device 注解 | `__host__ __device__` | `__aicore__`（SIMD 向量核）/ `__aiv__`（标量核） |
| 测试 | `test/std/<op>.pass.cpp` | `test/asc/std/<op>.pass.cpp` + kernel cannsim 仿真 |
| License | Apache-2.0 WITH LLVM-exception | Apache-2.0（复用 libc++ 则 + LLVM-exception） |
| 打包 | 研发态分发 | **`.run` 主交付** + CMake 包配置 + tar.gz |
