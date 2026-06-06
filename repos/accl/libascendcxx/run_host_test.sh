#!/bin/bash
# Host test for minmax. (生成自 core/scaffold_scripts.py)

# ---- 统一环境准备（core/scaffold_env.py 生成，host/kernel 共用）----
if command -v conda >/dev/null 2>&1; then
    source activate "${ASC_CONDA_ENV:-accl}" 2>/dev/null \
        || conda activate "${ASC_CONDA_ENV:-accl}" 2>/dev/null || true
fi
# ASCEND_HOME_PATH 可能由父进程预置，但 PATH/LD_LIBRARY_PATH 仍未完整
# 初始化；因此这里总是优先 source 官方 set_env.sh（幂等）。
for __f in "$ASCEND_ENV_SCRIPT" \
         /usr/local/Ascend/ascend-toolkit/set_env.sh \
         /usr/local/Ascend/cann/set_env.sh \
         "$HOME/Ascend/ascend-toolkit/set_env.sh"; do
    if [ -n "$__f" ] && [ -f "$__f" ]; then source "$__f"; break; fi
done
# llvm-objdump / cannsim 等只在 source set_env 后才上 PATH；父进程已设
# ASCEND_HOME_PATH 却缺这些目录时在此补齐。PATH 可以前置，库路径则
# 追加到官方 set_env.sh 之后，避免 devlib 抢在 lib64 前面导致 CANN
# 组件符号版本不匹配。
for __d in "$ASCEND_HOME_PATH/bin" "$ASCEND_HOME_PATH/tools/ccec_compiler/bin" \
         /usr/local/Ascend/cann/bin \
         /usr/local/Ascend/cann/x86_64-linux/bin \
         /usr/local/Ascend/cann/x86_64-linux/ccec_compiler/bin; do
    [ -d "$__d" ] && case ":$PATH:" in *":$__d:"*) ;; *) export PATH="$__d:$PATH";; esac
done
for __d in "$ASCEND_HOME_PATH/lib64" "$ASCEND_HOME_PATH/devlib" \
         "$ASCEND_HOME_PATH/x86_64-linux/lib64" "$ASCEND_HOME_PATH/x86_64-linux/devlib" \
         /usr/local/Ascend/cann/lib64 /usr/local/Ascend/cann/devlib \
         /usr/local/Ascend/cann/x86_64-linux/lib64 /usr/local/Ascend/cann/x86_64-linux/devlib \
         /usr/local/Ascend/driver/lib64 /usr/local/Ascend/driver/lib64/common \
         /usr/local/Ascend/driver/lib64/driver; do
    [ -d "$__d" ] && case ":$LD_LIBRARY_PATH:" in *":$__d:"*) ;; *) export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:+$LD_LIBRARY_PATH:}$__d";; esac
done
# ---- 环境准备结束 ----

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/build"
if [ -f "$BUILD_DIR/CMakeCache.txt" ] && ! grep -q "CMAKE_CACHEFILE_DIR:INTERNAL=$BUILD_DIR" "$BUILD_DIR/CMakeCache.txt"; then
    echo "[scaffold] stale CMake cache detected, cleaning build dir..."
    rm -rf "$BUILD_DIR"
fi
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"
cmake .. -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
make minmax_host_test
ctest -R "host\.minmax$" -V
