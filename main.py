"""ASC_agent 命令行入口。

子命令：
    convert  只做「生成 -> 写入目标仓库 -> 可选跑测试」，跳过 git 提交（推荐的全流程入口）
    run      迁移单个 CCCL 文件，含 git 提交检查与多轮修复（真实或 --mock）
    batch    按清单批量迁移并产出汇总报告（工具链 + 测试能力的核心）
    test     为指定算子生成并执行 host/kernel 测试
    folder-plan      扫描一个源目录并生成首批/后续迁移推荐计划
    folder-migrate   人工确认 folder-plan 后按批次执行闭包迁移
    dependency-convert  按依赖闭包 leaf-first 迁移一个 header（Node 12）
    api-map  独立逐文件提取 cuda/ 全树引用的外部 CUDA API，并映射本地晟腾 SIMT 文档
    selftest 用内置示例做一次离线冒烟（mock，无需仓库/网络）

用法：
    python main.py convert --input <CCCL 文件路径> --with-tests
    python main.py run     --input <CCCL 文件路径> [--mock] [--dry-run]
    python main.py batch   --manifest <manifest.yaml> [--mock] [--quiet]
    python main.py test    --input <CCCL 文件路径> [--host-only | --kernel-only]
    python main.py folder-plan --source-dir std/__algorithm --cccl-repo repos/cccl --real-ai
    python main.py folder-migrate --plan outputs/folder_migration_plan.json --batch first --approve --real-ai
    python main.py dependency-convert --entry-header __algorithm/all_of.h --plan-only
    python main.py api-map --prepare-only
    python main.py selftest
"""

from __future__ import annotations

import sys

from cli.commands import (  # noqa: F401
    _run_convert_test_loop,
    cmd_folder_migrate,
    cmd_test,
)

# Re-exported so existing callers / tests can keep using ``main.<symbol>``.
from cli.helpers import (  # noqa: F401
    DEFAULT_SETTINGS,
    PROJECT_ROOT,
    _build_test_feedback_text,
    _format_attempt_history,
    _maybe_migrate_tests,
    _record_migration_state,
    _run_operator_tests,
)
from cli.parser import build_parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
