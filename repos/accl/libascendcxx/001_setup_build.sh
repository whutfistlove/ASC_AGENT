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

set -e  # 遇到错误立即退出

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/build"

echo "🔧 Setting up build directory in: $BUILD_DIR"

# 创建 build 目录（如果不存在）
mkdir -p "$BUILD_DIR"

# 进入 build 目录并运行 CMake
cd "$BUILD_DIR"
cmake .. -DCMAKE_EXPORT_COMPILE_COMMANDS=ON

# 创建软链接到项目根目录（供 VS Code 使用）
if [ -f "compile_commands.json" ]; then
    ln -sf "$BUILD_DIR/compile_commands.json" "$SCRIPT_DIR/compile_commands.json"
    echo "✅ Created symlink: $SCRIPT_DIR/compile_commands.json -> $BUILD_DIR/compile_commands.json"
else
    echo "⚠️ Warning: compile_commands.json not found after CMake configure."
fi

echo "🎉 Build setup complete! You can now:"
echo "   - Open project in VS Code (IntelliSense should work)"
echo "   - Run 'cd build && make' to build"
echo "   - Run 'cd build && ctest -V' to test"