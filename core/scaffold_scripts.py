"""测试脚手架的 shell 脚本生成（与 C++ 源生成分离）。

从 operator_kernel_scaffold 抽出：kernel 仿真 run_test.sh、host 单测脚本、full_project
脚本。三者都嵌入统一的 env 片段（core/scaffold_env），并复用 main.cpp 里约定的判定标记
（KERNEL_*_MARKER，定义在 operator_kernel_scaffold，由 C++ 侧产出、脚本侧 grep）。
"""

from __future__ import annotations

from core.operator_kernel_scaffold import (
    KERNEL_CANNSIM_SOC_VERSION,
    KERNEL_PASS_MARKER,
    KERNEL_SMOKE_MARKER,
    KERNEL_VERIFY_MARKER,
)
from core.scaffold_env import env_setup_block


def stale_cache_guard(build_var: str = "BUILD_DIR") -> str:
    """一段 bash：当 build 缓存记录的目录与当前不符时清理（手动运行也健壮）。"""
    return (
        f'if [ -f "${build_var}/CMakeCache.txt" ] && '
        f'! grep -q "CMAKE_CACHEFILE_DIR:INTERNAL=${build_var}" "${build_var}/CMakeCache.txt"; then\n'
        '    echo "[scaffold] stale CMake cache detected, cleaning build dir..."\n'
        f'    rm -rf "${build_var}"\n'
        "fi\n"
    )


def run_test_sh(algo: str) -> str:
    """kernel 仿真脚本：环境准备 + 构建 + cannsim 录制 + 基于 cannsim.log 的真实判定。"""
    return (
        "#!/bin/bash\n"
        f"# Kernel simulation test for {algo}. (生成自 core/scaffold_scripts.py)\n\n"
        + env_setup_block()
        + "\n"
        "set -e  # Exit on any error\n\n"
        'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
        'PROJECT_ROOT="$SCRIPT_DIR/../../../../.."\n'
        'SRC_INCLUDE_DIR="$PROJECT_ROOT/include/ascend"\n'
        'DST_KERNEL_SYMLINK="$SCRIPT_DIR/ascend"\n\n'
        'if [ ! -d "$SRC_INCLUDE_DIR" ]; then\n'
        '    echo "ERROR: source header dir not found: $SRC_INCLUDE_DIR"\n'
        "    exit 1\n"
        "fi\n\n"
        'ln -sfn "$SRC_INCLUDE_DIR" "$DST_KERNEL_SYMLINK"\n'
        'rm -rf "$SCRIPT_DIR/build"\n'
        'mkdir -p "$SCRIPT_DIR/build"\n'
        'cd "$SCRIPT_DIR/build"\n'
        'export CPLUS_INCLUDE_PATH="$SCRIPT_DIR:$CPLUS_INCLUDE_PATH"\n\n'
        'cmake .. || { echo "ERROR: CMake configure failed"; rm -f "$DST_KERNEL_SYMLINK"; exit 1; }\n'
        'make -j"$(nproc)" || { echo "ERROR: build failed"; rm -f "$DST_KERNEL_SYMLINK"; exit 1; }\n\n'
        'rm -f "$DST_KERNEL_SYMLINK"\n'
        'export LD_LIBRARY_PATH="$PWD/lib:$LD_LIBRARY_PATH"\n\n'
        "if ! command -v cannsim &> /dev/null; then\n"
        '    echo "ERROR: cannsim command not found. Please install/enable the CANN simulator."\n'
        "    exit 1\n"
        "fi\n\n"
        f"cannsim record ./ascendc_kernels_bbit -s {KERNEL_CANNSIM_SOC_VERSION} --gen-report \\\n"
        '    || { echo "ERROR: cannsim simulation failed"; exit 1; }\n\n'
        f'echo "kernel simulation for {algo} finished."\n\n'
        "# cannsim 把被测程序的 stdout 重定向到 build/cannsim_*/cannsim.log。\n"
        "# 因此「通过」必须基于程序真实的数值校验(独立 golden 全中)，而不是\n"
        "# cannsim 录制成功本身 —— 否则数值算错也会被掩盖成假绿(见问题①)。\n"
        'SIM_LOG="$(ls -t "$SCRIPT_DIR"/build/cannsim_*/cannsim.log 2>/dev/null | head -1)"\n'
        'if [ -z "$SIM_LOG" ] || [ ! -f "$SIM_LOG" ]; then\n'
        '    echo "ERROR: cannsim.log not found; cannot confirm numeric verification"\n'
        "    exit 1\n"
        "fi\n"
        'if grep -qF "Mismatch at" "$SIM_LOG"; then\n'
        '    echo "ERROR: kernel numeric mismatch detected in $SIM_LOG"\n'
        '    tail -n 200 "$SIM_LOG"\n'
        "    exit 1\n"
        "fi\n"
        f'if grep -qF "{KERNEL_VERIFY_MARKER}" "$SIM_LOG"; then\n'
        f'    echo "{KERNEL_PASS_MARKER}"\n'
        f'elif grep -qF "{KERNEL_SMOKE_MARKER}" "$SIM_LOG"; then\n'
        '    echo "KERNEL_SIM_RESULT: SMOKE (no kernel_spec; semantic golden check skipped)"\n'
        "else\n"
        '    echo "ERROR: kernel verification marker not found in $SIM_LOG"\n'
        '    tail -n 200 "$SIM_LOG"\n'
        "    exit 1\n"
        "fi\n"
    )


def host_run_test_sh(algo: str) -> str:
    """host 单测脚本：环境准备 + 配置 + 仅编译该算子 host 测试 + 跑对应 ctest。

    在 libascendcxx 目录下运行，取代签入的 000_set_env.sh + 001_setup_build.sh。
    """
    pattern = f"host\\.{algo}$"
    return (
        "#!/bin/bash\n"
        f"# Host test for {algo}. (生成自 core/scaffold_scripts.py)\n\n"
        + env_setup_block()
        + "\n"
        "set -e\n"
        'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
        'BUILD_DIR="$SCRIPT_DIR/build"\n'
        + stale_cache_guard()
        + 'mkdir -p "$BUILD_DIR"\n'
        'cd "$BUILD_DIR"\n'
        "cmake .. -DCMAKE_EXPORT_COMPILE_COMMANDS=ON\n"
        f"make {algo}_host_test\n"
        f'ctest -R "{pattern}" -V\n'
    )


def full_project_run_sh(algo: str) -> str:
    """full_project 模式脚本：环境准备 + 全项目配置编译 + 跑该算子 kernel.sim 测试。

    取代签入的 000_set_env.sh + 004_build_cmake_test_host_cannsim.sh。
    """
    pattern = f"kernel\\.{algo}\\.sim$"
    return (
        "#!/bin/bash\n"
        f"# Full-project kernel sim for {algo}. (生成自 core/scaffold_scripts.py)\n\n"
        + env_setup_block()
        + "\n"
        "set -e\n"
        'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
        'BUILD_DIR="$SCRIPT_DIR/build"\n'
        + stale_cache_guard()
        + 'mkdir -p "$BUILD_DIR"\n'
        'cd "$BUILD_DIR"\n'
        "cmake .. -DCMAKE_BUILD_TYPE=Debug -DBUILD_TESTING=ON\n"
        'make -j"$(nproc)"\n'
        f'ctest -R "{pattern}" -V\n'
    )
