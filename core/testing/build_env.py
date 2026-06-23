"""构建环境探测与修复（host/kernel 测试共用的"读环境"工具）。

从 OperatorTestRunner 抽出的一组纯函数：判断 CANN 工具是否可达、为缺失工具补出
PATH 目录、清理项目改名/移动后残留的过期 CMake 缓存。无状态、易单测，运行器只需调用。
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

# CANN 仿真所需、但常只在 source set_env 后才上 PATH 的工具。
_KERNEL_TOOLS = ("llvm-objdump", "cannsim")


def cann_bin_candidates() -> list[Path]:
    """CANN set_env.sh 会加进 PATH 的 bin 目录（此刻可能还没 source）。"""
    cands: list[Path] = []
    home = os.environ.get("ASCEND_HOME_PATH", "")
    if home:
        cands += [
            Path(home) / "bin",
            Path(home) / "python" / "site-packages" / "bin",
            Path(home) / "tools" / "ccec_compiler" / "bin",
        ]
    bases = [Path("/usr/local/Ascend/cann"), Path("/usr/local/Ascend/ascend-toolkit")]
    bases.extend(sorted(Path("/usr/local/Ascend").glob("cann-*")))
    for base in bases:
        cands += [
            base / "bin",
            base / "python" / "site-packages" / "bin",
            base / "x86_64-linux" / "bin",
            base / "x86_64-linux" / "ccec_compiler" / "bin",
            base / "tools" / "ccec_compiler" / "bin",
        ]
    return cands


def tool_reachable(name: str) -> bool:
    """工具能否被找到：PATH 上，或在 CANN 安装目录里（set_env 会把它带进 PATH）。"""
    if shutil.which(name):
        return True
    return any((d / name).exists() for d in cann_bin_candidates())


def missing_kernel_tools() -> list[str]:
    """kernel 仿真所需但确实不可用的工具（用于 SKIPPED 预检）。

    cannsim 缺失则仿真无从谈起。注意 cannsim/llvm-objdump 常只在 source set_env 后才上
    PATH，所以这里同时探测 CANN 安装目录，避免把"装了但没 source"误判为缺失。
    """
    return [] if tool_reachable("cannsim") else ["cannsim"]


def cann_path_additions() -> list[str]:
    """为不在 PATH 上的 kernel 工具（llvm-objdump / cannsim）补出的 CANN bin 目录。

    run_test.sh 只在 ASCEND_HOME_PATH 为空时才 source set_env.sh；父进程已设该变量却缺
    这些 bin 目录时，会找不到 llvm-objdump / cannsim（见 outputs/kernel_test_*.log）。
    """
    dirs: list[str] = []
    for name in _KERNEL_TOOLS:
        if shutil.which(name):
            continue
        for d in cann_bin_candidates():
            if (d / name).exists():
                if str(d) not in dirs:
                    dirs.append(str(d))
                break
    return dirs


def remove_stale_cmake_cache(build_dir: Path) -> bool:
    """清理记录了旧构建目录的 CMake 缓存（典型：项目被改名/移动后旧缓存残留）。

    当 ``build/CMakeCache.txt`` 里记录的 ``CMAKE_CACHEFILE_DIR`` 与当前 build 目录不一致
    时，cmake 会直接报错（见 outputs/host_test_*.log）。这里在执行前主动删除整个 build
    目录，让 cmake 重新配置。返回是否清理过。生成脚本里也内置了同等的 bash 守卫
    （KernelScaffoldBuilder._stale_cache_guard），手动运行同样健壮。
    """
    cache = build_dir / "CMakeCache.txt"
    if not cache.exists():
        return False
    try:
        text = cache.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    cached_dir = ""
    for line in text.splitlines():
        if line.startswith("CMAKE_CACHEFILE_DIR:"):
            cached_dir = line.split("=", 1)[-1].strip()
            break
    expected = Path(build_dir).resolve().as_posix()
    if cached_dir and Path(cached_dir).as_posix() != expected:
        shutil.rmtree(build_dir, ignore_errors=True)
        return True
    return False
