#!/bin/bash
# Kernel simulation test for min.

if [ -z "$ASCEND_HOME_PATH" ]; then
    if [ -f "/usr/local/Ascend/cann/set_env.sh" ]; then
        source /usr/local/Ascend/cann/set_env.sh
    elif [ -f "/usr/local/Ascend/ascend-toolkit/set_env.sh" ]; then
        source /usr/local/Ascend/ascend-toolkit/set_env.sh
    fi
fi
if [ -d "/usr/local/Ascend/cann/x86_64-linux/lib64" ]; then
    export LD_LIBRARY_PATH="/usr/local/Ascend/cann/x86_64-linux/lib64:$LD_LIBRARY_PATH"
fi

set -e  # Exit on any error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR/../../../../.."
SRC_INCLUDE_DIR="$PROJECT_ROOT/include/ascend"
DST_KERNEL_SYMLINK="$SCRIPT_DIR/ascend"

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

echo "kernel simulation for min finished."

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
    exit 1
fi
if grep -qF "kernel simulation verification passed." "$SIM_LOG"; then
    echo "KERNEL_SIM_RESULT: PASS"
elif grep -qF "SMOKE-ONLY" "$SIM_LOG"; then
    echo "KERNEL_SIM_RESULT: SMOKE (no kernel_spec; semantic golden check skipped)"
else
    echo "ERROR: kernel verification marker not found in $SIM_LOG"
    exit 1
fi
