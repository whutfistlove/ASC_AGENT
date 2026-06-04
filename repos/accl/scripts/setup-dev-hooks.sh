#!/bin/bash
# *****************************************************************************
# Copyright (c) 2026 Xiong Shengwu Group at Wuhan University of Technology. All Rights Reserved.
# Author: Lu Xiongbo <luxiongbo@whut.edu.cn>
# Create: 2026-01-18
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

set -e

echo "🔧 Setting up development environment..."

# 安装 pre-commit（如果未安装）
if ! command -v pre-commit &> /dev/null; then
    echo "📦 Installing pre-commit..."
    pip install --user pre-commit
fi

# 安装 Git hook
echo "🔗 Installing Git pre-commit hook..."
pre-commit install

echo "✅ Done! Copyright headers will be added automatically on commit."