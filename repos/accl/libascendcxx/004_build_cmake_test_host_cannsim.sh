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

set -e  # 遇到任何错误立即退出

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/build"

# ===== 可选：清理旧构建（取消注释下一行即可启用）=====
# rm -rf "$BUILD_DIR"

# 创建构建目录
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

# 配置项目（启用测试）
echo "🔧 Configuring project with CMake..."
cmake .. -DCMAKE_BUILD_TYPE=Debug -DBUILD_TESTING=ON

# 编译
echo "🔨 Building project..."
make -j$(nproc)

# 运行测试（包括 host + kernel simulation）
echo "🧪 Running tests with ctest -V..."
ctest -V

echo "✅ All done!"


echo "只运行 max 相关的所有测试 host + kernel.sim "
echo "ctest -R max -V"

echo "只运行 host 端的 max 测试"
echo "ctest -R "host\.max" -V"

echo "只运行 kernel 仿真的 max 测试"
echo "ctest -R "kernel\.max\.sim" -V"