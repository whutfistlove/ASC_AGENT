#!/bin/bash

# *****************************************************************************
# Copyright (c) 2026 Xiong Shengwu Group at Wuhan University of Technology. All Rights Reserved.
# Author: Lu Xiongbo <luxiongbo@whut.edu.cn>
# Create: 2026-01-19
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# *****************************************************************************

set -e  # Exit on any error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/build"

echo "🚀 Preparing CANN Sim environment..."

# === 关键：启用 CANN 模拟器模式 ===
export ASCEND_SIMULATOR_MODE=1
export ASCEND_SLOG_PRINT_TO_STDOUT=1
export ASCEND_GLOBAL_LOG_LEVEL=3

# 自动探测 ASCEND_HOME（兼容默认安装路径）
if [ -z "$ASCEND_HOME" ]; then
    if [ -d "/usr/local/Ascend/ascend-toolkit/latest" ]; then
        export ASCEND_HOME="/usr/local/Ascend/ascend-toolkit/latest"
    else
        echo "⚠️ Warning: ASCEND_HOME not set and default path not found."
        echo "   Please ensure CANN Toolkit is installed."
    fi
fi

if [ -n "$ASCEND_HOME" ]; then
    export ASCEND_OPP_PATH="$ASCEND_HOME/opp"
    export LD_LIBRARY_PATH="$ASCEND_HOME/lib64:$LD_LIBRARY_PATH"
fi

echo "🔧 Using ASCEND_HOME: ${ASCEND_HOME:-<not set>}"
echo "🧪 Simulator mode: ENABLED (ASCEND_SIMULATOR_MODE=1)"

# === 进入 build 目录 ===
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

# === 配置 CMake（启用测试）===
echo "⚙️ Configuring CMake..."
cmake .. -DLIBASCENDCXX_BUILD_TESTS=ON

# === 构建 device 测试 ===
echo "📦 Building max_device_test..."
make max_device_test -j$(nproc)

# === 运行测试 ===
echo "🧪 Running device test in CANN Sim mode..."
./test/libascendcxx/max_device_test

echo "✅ Device test completed successfully!"