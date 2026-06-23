"""测试脚手架的统一环境准备片段（host 与 kernel 共用，单一事实源）。

历史上 host 侧靠签入的 000_set_env.sh、kernel 侧靠 run_test.sh 内联各写一套环境准备，
两者还不一致（conda 激活、Ascend env 探测、工具 PATH 各搞各的），改名/换机后容易漂移。
这里把"激活 conda（可选）+ source Ascend 环境 + 把 llvm-objdump/cannsim/lib64 补进
PATH"收敛成**一个** Python 函数，host 与 kernel 的生成脚本都嵌入它，保证两侧同源。
"""

from __future__ import annotations


def env_setup_block() -> str:
    """返回一段可嵌入生成脚本的 bash：准备 conda + Ascend + 工具 PATH。

    幂等、容错（找不到就跳过并继续），不带 ``set -e``，由调用脚本自行决定。
    可用环境变量覆盖：``ASC_CONDA_ENV``（conda 环境名）、``ASCEND_ENV_SCRIPT``
    （Ascend set_env 脚本路径）。
    """
    return (
        "# ---- 统一环境准备（core/scaffold_env.py 生成，host/kernel 共用）----\n"
        'for __conda_sh in "$CONDA_SH" "$HOME/miniforge3/etc/profile.d/conda.sh" \\\n'
        '                  "$HOME/miniconda3/etc/profile.d/conda.sh" "$HOME/anaconda3/etc/profile.d/conda.sh"; do\n'
        '    if [ -n "$__conda_sh" ] && [ -f "$__conda_sh" ]; then source "$__conda_sh"; break; fi\n'
        "done\n"
        'if command -v conda >/dev/null 2>&1; then\n'
        '    source activate "${ASC_CONDA_ENV:-asc-agent}" 2>/dev/null \\\n'
        '        || conda activate "${ASC_CONDA_ENV:-asc-agent}" 2>/dev/null || true\n'
        "fi\n"
        "# ASCEND_HOME_PATH 可能由父进程预置，但 PATH/LD_LIBRARY_PATH 仍未完整\n"
        "# 初始化；因此这里总是优先 source 官方 set_env.sh（幂等）。\n"
        'for __f in "$ASCEND_ENV_SCRIPT" \\\n'
        '         "$ASCEND_HOME_PATH/set_env.sh" \\\n'
        "         /usr/local/Ascend/ascend-toolkit/set_env.sh \\\n"
        "         /usr/local/Ascend/cann/set_env.sh \\\n"
        "         /usr/local/Ascend/cann-9.0.0/set_env.sh \\\n"
        '         "$HOME/Ascend/ascend-toolkit/set_env.sh"; do\n'
        '    if [ -n "$__f" ] && [ -f "$__f" ]; then source "$__f"; break; fi\n'
        "done\n"
        "# llvm-objdump / cannsim 等只在 source set_env 后才上 PATH；父进程已设\n"
        "# ASCEND_HOME_PATH 却缺这些目录时在此补齐。PATH 可以前置，库路径则\n"
        "# 追加到官方 set_env.sh 之后，避免 devlib 抢在 lib64 前面导致 CANN\n"
        "# 组件符号版本不匹配。\n"
        'for __d in "$ASCEND_HOME_PATH/bin" "$ASCEND_HOME_PATH/tools/ccec_compiler/bin" \\\n'
        "         /usr/local/Ascend/cann/bin \\\n"
        "         /usr/local/Ascend/cann/x86_64-linux/bin \\\n"
        "         /usr/local/Ascend/cann/python/site-packages/bin \\\n"
        "         /usr/local/Ascend/cann/x86_64-linux/ccec_compiler/bin; do\n"
        '    [ -d "$__d" ] && case ":$PATH:" in *":$__d:"*) ;; *) export PATH="$__d:$PATH";; esac\n'
        "done\n"
        'for __d in "$ASCEND_HOME_PATH/lib64" "$ASCEND_HOME_PATH/devlib" \\\n'
        '         "$ASCEND_HOME_PATH/x86_64-linux/lib64" "$ASCEND_HOME_PATH/x86_64-linux/devlib" \\\n'
        "         /usr/local/Ascend/cann/lib64 /usr/local/Ascend/cann/devlib \\\n"
        "         /usr/local/Ascend/cann/x86_64-linux/lib64 /usr/local/Ascend/cann/x86_64-linux/devlib \\\n"
        "         /usr/local/Ascend/driver/lib64 /usr/local/Ascend/driver/lib64/common \\\n"
        "         /usr/local/Ascend/driver/lib64/driver; do\n"
        '    [ -d "$__d" ] && case ":$LD_LIBRARY_PATH:" in *":$__d:"*) ;; *) export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:+$LD_LIBRARY_PATH:}$__d";; esac\n'
        "done\n"
        'for __d in "$ASCEND_HOME_PATH/python/site-packages" /usr/local/Ascend/cann/python/site-packages; do\n'
        '    [ -d "$__d" ] && case ":$PYTHONPATH:" in *":$__d:"*) ;; *) export PYTHONPATH="$__d${PYTHONPATH:+:$PYTHONPATH}";; esac\n'
        "done\n"
        "# ---- 环境准备结束 ----\n"
    )
