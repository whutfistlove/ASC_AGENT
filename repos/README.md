# repos/ — ASC_agent 内置的源仓库与目标仓库

为了让「CCCL→ACCL 转换 + 测试迁移 + host/kernel 仿真测试」整条链路在**单一项目内**跑通，
这里内置了两个仓库（各放了几个示例文件）：

```text
repos/
├── cccl/                                  # 源仓库（libcu++ 风格头文件 + 平行 test 树）
│   └── libcudacxx/
│       ├── include/cuda/std/
│       │   ├── __algorithm/{max,min,swap,clamp,minmax,quad_fanout}.h
│       │   │                                               # 算子头（待迁移）
│       │   ├── __numeric/{gcd,lcm,midpoint}.h             # 数值算子（二元/整数）
│       │   └── __cccl/os.h                                # 宏类头文件示例
│       └── test/std/                                       # CCCL 侧测试（语义基准，给模型迁移）
│           ├── __algorithm/{max,min,swap,clamp,minmax,quad_fanout}.pass.cpp
│           │                                               # 头 <op>.h ↔ 测试 <op>.pass.cpp
│           └── __numeric/{gcd,lcm,midpoint}.pass.cpp
└── accl/                                  # 目标仓库（= 原 mylearn 的 libascendcxx，已整合测试链路）
    ├── .clang-format / CPPLINT.cfg / .pre-commit-config.yaml
    ├── scripts/                           # 版权头 hook + CANN 风格检查脚本
    └── libascendcxx/
        ├── 000_set_env.sh ... 004_*.sh    # host / kernel 仿真构建脚本
        ├── CMakeLists.txt                 # 顶层（INTERFACE 头文件库 + 测试）
        ├── include/ascend/std/            # 目标头文件（已含 __config / algorithm / max.h）
        └── test/libascendcxx/             # host / device / kernel 测试（CMake 自动扫描）
            └── ascend/
                ├── host/<algo>_tests.cpp           -> ctest 名 host.<algo>
                ├── device/<algo>_tests.cpp
                └── kernel/<algo>_example/run_test.sh -> ctest 名 kernel.<algo>.sim
```

## 关键约定

- **源前缀**：`libcudacxx/include/cuda/std`，**目标前缀**：`libascendcxx/include/ascend/std`，
  目录段 `__cccl → __accl`（见 `config/settings.yaml` 的 `mapping`）。
- **CCCL 测试前缀**：`libcudacxx/test/std`，后缀 `.pass.cpp`：算子头 `__algorithm/<op>.h` 的测试源
  约定为 `libcudacxx/test/std/__algorithm/<op>.pass.cpp`（见 `mapping.cccl_test_prefix`）。
- 转换后的目标文件会写到 `accl/<target_relpath>`，例如
  `repos/accl/libascendcxx/include/ascend/std/__algorithm/min.h`。
- **测试代码由大模型按算子迁移**（CCCL 测试 → ACCL host 测试 + kernel_spec），不再是写死模板；
  host 测试逐条打印数值、kernel 测试 = 固定脚手架 + 模型槽位。详见 [../docs/guide.md](../docs/guide.md)。
- host 测试：CMake 扫描 `ascend/host/*_tests.cpp`，用例名 `host.<algo>`。
- kernel 仿真：CMake 扫描 `ascend/kernel/*_example/run_test.sh`，用例名 `kernel.<algo>.sim`，
  内部用 `cannsim` 跑仿真。
- host 端编译/链接只依赖标准 C++，可在普通 Linux 上跑；
  kernel 仿真需要 CANN 工具链 + `cannsim`（通常在 Ascend 机器）。

