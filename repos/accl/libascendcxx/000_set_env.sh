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

# ---------------------------------------------------------------------------
# 环境激活（整合进 cccl-to-accl 项目后，改为可移植写法：
#   - conda 环境名可用 ASC_CONDA_ENV 覆盖，默认 asc_cccl_env；
#   - Ascend 环境脚本路径可用 ASCEND_ENV_SCRIPT 覆盖；找不到则尝试常见位置；
#   - 缺失时给出警告而不是直接 fail，方便只跑 host 编译自检的场景。）
# ---------------------------------------------------------------------------
ASC_CONDA_ENV="${ASC_CONDA_ENV:-asc_cccl_env}"
if command -v conda >/dev/null 2>&1; then
    # shellcheck disable=SC1091
    source activate "$ASC_CONDA_ENV" 2>/dev/null \
        || conda activate "$ASC_CONDA_ENV" 2>/dev/null \
        || echo "⚠️  无法激活 conda 环境 $ASC_CONDA_ENV，沿用当前环境。"
else
    echo "⚠️  未检测到 conda，沿用当前 Python/编译环境。"
fi

ASCEND_ENV_SCRIPT="${ASCEND_ENV_SCRIPT:-}"
if [ -z "$ASCEND_ENV_SCRIPT" ]; then
    for cand in \
        /home/admin1/work/command/set_ascend_env.sh \
        /usr/local/Ascend/ascend-toolkit/set_env.sh \
        "$HOME/Ascend/ascend-toolkit/set_env.sh"; do
        if [ -f "$cand" ]; then
            ASCEND_ENV_SCRIPT="$cand"
            break
        fi
    done
fi
if [ -n "$ASCEND_ENV_SCRIPT" ] && [ -f "$ASCEND_ENV_SCRIPT" ]; then
    # shellcheck disable=SC1090
    source "$ASCEND_ENV_SCRIPT"
else
    echo "⚠️  未找到 Ascend 环境脚本（可用 ASCEND_ENV_SCRIPT 指定）。kernel 仿真可能不可用。"
fi
