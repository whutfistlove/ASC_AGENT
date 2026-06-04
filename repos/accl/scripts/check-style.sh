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
# scripts/check-style.sh - 本地执行 CANN 风格检查（对标 ops-nn）

set -e

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

echo "🔍 步骤 1: 检查 clang-format"

# 自动找 clang-format（14～18）
CLANG_FORMAT=""
for ver in 18 17 16 15 14; do
    if command -v "clang-format-$ver" &>/dev/null; then
        CLANG_FORMAT="clang-format-$ver"
        break
    fi
done
CLANG_FORMAT=${CLANG_FORMAT:-clang-format}

if ! command -v "$CLANG_FORMAT" &>/dev/null; then
    echo "❌ 请安装 clang-format（推荐 14+）"
    exit 1
fi

# 只检查 C/C++ 头文件（CCCL 风格：纯头文件库）
SOURCES=$(git ls-files 'include/**/*.h' 'include/**/*.hpp' 'include/**/*.cuh' '*.h' '*.hpp' '*.cuh' 2>/dev/null || true)

if [ -z "$SOURCES" ]; then
    echo "⚠️ 未找到 C/C++ 头文件，跳过格式检查"
else
    BAD_FILES=$(
        echo "$SOURCES" | xargs "$CLANG_FORMAT" --dry-run --Werror 2>&1 | \
        grep -E '.*\.(h|hpp|cuh):' | cut -d: -f1 || true
    )
    if [ -n "$BAD_FILES" ]; then
        echo "❌ 以下文件不符合 CANN .clang-format 规范："
        echo "$BAD_FILES" | sort -u
        echo "💡 一键修复: $CLANG_FORMAT -i \$(git ls-files '*.h' '*.hpp' '*.cuh')"
        exit 1
    fi
fi
echo "✅ clang-format 检查通过"

echo "🔍 步骤 2: 静态检查 (cpplint)"
if [ -n "$SOURCES" ]; then
    cpplint --extensions=h,hpp,cuh --quiet $SOURCES || {
        echo "❌ cpplint 检查失败"
        exit 1
    }
fi
echo "✅ cpplint 检查通过"

echo "🎉 所有代码规范检查通过！"