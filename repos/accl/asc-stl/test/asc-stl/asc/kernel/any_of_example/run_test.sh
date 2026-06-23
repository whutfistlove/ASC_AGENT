#!/bin/bash
# Kernel simulation test for any_of. (生成自 core/scaffold_scripts.py)

# ---- 统一环境准备（core/scaffold_env.py 生成，host/kernel 共用）----
for __conda_sh in "$CONDA_SH" "$HOME/miniforge3/etc/profile.d/conda.sh" \
                  "$HOME/miniconda3/etc/profile.d/conda.sh" "$HOME/anaconda3/etc/profile.d/conda.sh"; do
    if [ -n "$__conda_sh" ] && [ -f "$__conda_sh" ]; then source "$__conda_sh"; break; fi
done
if command -v conda >/dev/null 2>&1; then
    source activate "${ASC_CONDA_ENV:-asc-agent}" 2>/dev/null \
        || conda activate "${ASC_CONDA_ENV:-asc-agent}" 2>/dev/null || true
fi
# ASCEND_HOME_PATH 可能由父进程预置，但 PATH/LD_LIBRARY_PATH 仍未完整
# 初始化；因此这里总是优先 source 官方 set_env.sh（幂等）。
for __f in "$ASCEND_ENV_SCRIPT" \
         "$ASCEND_HOME_PATH/set_env.sh" \
         /usr/local/Ascend/ascend-toolkit/set_env.sh \
         /usr/local/Ascend/cann/set_env.sh \
         /usr/local/Ascend/cann-9.0.0/set_env.sh \
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
         /usr/local/Ascend/cann/python/site-packages/bin \
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
for __d in "$ASCEND_HOME_PATH/python/site-packages" /usr/local/Ascend/cann/python/site-packages; do
    [ -d "$__d" ] && case ":$PYTHONPATH:" in *":$__d:"*) ;; *) export PYTHONPATH="$__d${PYTHONPATH:+:$PYTHONPATH}";; esac
done
# ---- 环境准备结束 ----

set -e  # Exit on any error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR/../../../../.."
SRC_INCLUDE_DIR="$PROJECT_ROOT/include/asc"
DST_KERNEL_SYMLINK="$SCRIPT_DIR/asc"

if [ ! -d "$SRC_INCLUDE_DIR" ]; then
    echo "ERROR: source header dir not found: $SRC_INCLUDE_DIR"
    exit 1
fi

ln -sfn "$SRC_INCLUDE_DIR" "$DST_KERNEL_SYMLINK"
rm -rf "$SCRIPT_DIR/build"
mkdir -p "$SCRIPT_DIR/build"
cd "$SCRIPT_DIR/build"
export CPLUS_INCLUDE_PATH="$SCRIPT_DIR:$CPLUS_INCLUDE_PATH"

cmake .. || { echo "ERROR: CMake configure failed"; rm -f "$DST_KERNEL_SYMLINK"; exit 1; }
make -j"$(nproc)" || { echo "ERROR: build failed"; rm -f "$DST_KERNEL_SYMLINK"; exit 1; }

rm -f "$DST_KERNEL_SYMLINK"
export LD_LIBRARY_PATH="$PWD/lib:$LD_LIBRARY_PATH"

if ! command -v cannsim &> /dev/null; then
    echo "ERROR: cannsim command not found. Please install/enable the CANN simulator."
    exit 1
fi

cannsim record ./ascendc_kernels_bbit -s Ascend950 --gen-report \
    || { echo "ERROR: cannsim simulation failed"; exit 1; }

echo "kernel simulation for any_of finished."

# cannsim 把被测程序的 stdout 重定向到 build/cannsim_*/cannsim.log。
# 因此「通过」必须基于程序真实的数值校验(独立 golden 全中)，而不是
# cannsim 录制成功本身 —— 否则数值算错也会被掩盖成假绿(见问题①)。
SIM_LOG="$(ls -t "$SCRIPT_DIR"/build/cannsim_*/cannsim.log 2>/dev/null | head -1)"
if [ -z "$SIM_LOG" ] || [ ! -f "$SIM_LOG" ]; then
    echo "ERROR: cannsim.log not found; cannot confirm numeric verification"
    exit 1
fi
if grep -qF "Mismatch at" "$SIM_LOG"; then
    echo "ERROR: kernel numeric mismatch detected in $SIM_LOG"
    tail -n 200 "$SIM_LOG"
    exit 1
fi
if grep -qF "kernel simulation verification passed." "$SIM_LOG"; then
    echo "kernel simulation verification passed."
    echo "KERNEL_SIM_RESULT: PASS"
elif grep -qF "SMOKE-ONLY" "$SIM_LOG"; then
    echo "KERNEL_SIM_RESULT: SMOKE (no kernel_spec; semantic golden check skipped)"
else
    echo "ERROR: kernel verification marker not found in $SIM_LOG"
    tail -n 200 "$SIM_LOG"
    exit 1
fi
