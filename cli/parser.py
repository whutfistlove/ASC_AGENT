"""Argument parser wiring for the ASC_agent CLI."""
from __future__ import annotations

import argparse

from cli.commands import (
    cmd_batch,
    cmd_convert,
    cmd_dep_graph,
    cmd_dependency_convert,
    cmd_folder_migrate,
    cmd_folder_plan,
    cmd_inventory,
    cmd_make_example,
    cmd_migration_context,
    cmd_migration_status,
    cmd_package_migrate,
    cmd_package_plan,
    cmd_revalidate_samples,
    cmd_run,
    cmd_selftest,
    cmd_test,
    cmd_test_index,
    cmd_test_migrate,
    cmd_test_plan,
)
from core.planning.folder_planner import DEFAULT_FOLDER_PLAN_JSON, DEFAULT_FOLDER_PLAN_MD
from core.planning.package_planner import DEFAULT_PACKAGE_PLAN_JSON, DEFAULT_PACKAGE_PLAN_MD


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CCCL -> ACCL v3 迁移工具链")
    parser.add_argument("--settings", help="settings.yaml 路径（默认 config/settings.yaml）")
    sub = parser.add_subparsers(dest="command", required=True)
    cccl_repo_help = "真实 CCCL 仓库根目录；默认取 config/settings.yaml 的 paths.cccl_repo（通常为 repos/cccl，可由 CCCL_REPO 覆盖）"

    def add_test_flags(p, include_with_tests: bool = True):
        if include_with_tests:
            p.add_argument("--with-tests", action="store_true", help="迁移完成后自动生成并执行算子测试")
        p.add_argument("--host-only", action="store_true", help="只执行 host 侧测试")
        p.add_argument("--kernel-only", action="store_true", help="只执行 kernel 侧测试")
        p.add_argument(
            "--kernel-mode",
            choices=("run_test", "full_project"),
            default="run_test",
            help="kernel 测试模式：run_test(只跑算子目录) / full_project(走 004 全项目)",
        )
        p.add_argument("--prepare-tests-only", action="store_true", help="仅生成测试文件，不执行测试命令")
        p.add_argument("--overwrite-tests", action="store_true", help="覆盖已存在的测试文件")
        p.add_argument(
            "--kernel-fast",
            action="store_true",
            help="kernel 快速档：workload 降到 1 核 1 tile(64 元素)，camodel 数十秒可完成（CI/冒烟）。默认关闭，最终验证用完整档。",
        )
        p.add_argument(
            "--kernel-timeout",
            type=int,
            default=0,
            help="kernel 测试超时秒数（0=取 tests.kernel_timeout_sec，默认 1200）",
        )
        p.add_argument(
            "--kernel-print-samples",
            type=int,
            default=None,
            help="kernel 日志逐元素打印多少条用例（默认 8；-1=全部；0=只留汇总）",
        )
        p.add_argument("--test-dry-run", action="store_true", help="打印并落盘测试命令，但不真正执行")
        p.add_argument(
            "--test-feedback-to-model",
            action="store_true",
            help="当测试失败时，将测试日志回传模型并生成一版修复稿（写入 outputs）",
        )
        p.add_argument(
            "--test-feedback-skill",
            default="rewrite_fix_from_log_and_test.md",
            help="测试反馈修复时使用的 skill 文件名",
        )

    def common(p):
        p.add_argument("--mock", action="store_true", help="使用 mock 模型与假提交检查（离线）")
        p.add_argument("--dry-run", action="store_true", help="真实模型但不执行 git/clang，仅记录命令")
        p.add_argument("--mock-rounds", type=int, default=0, help="mock 模式下需要几轮修复才通过")
        p.add_argument(
            "--max-fix-rounds", type=int, default=0,
            help="convert 测试反馈闭环的最大修复轮数（0=取 retry.max_fix_rounds，默认 5）",
        )
        p.add_argument("--quiet", action="store_true", help="减少日志输出")
        p.add_argument("--require-push", action="store_true", help="未成功 push 时返回非零退出码")
        p.add_argument(
            "--show-model-io",
            action="store_true",
            help="打印每次与模型的完整对话（system 提示词 + 发送的请求 + 模型原始响应）",
        )
        add_test_flags(p)

    p_run = sub.add_parser("run", help="迁移单个文件")
    p_run.add_argument("--input", required=True, help="待迁移的 CCCL 文件路径")
    common(p_run)
    p_run.set_defaults(func=cmd_run)

    p_convert = sub.add_parser(
        "convert", help="只生成并写入目标仓库（跳过 git 提交），可选直接跑 host/kernel 测试"
    )
    p_convert.add_argument("--input", required=True, help="待迁移的 CCCL 文件路径")
    p_convert.add_argument(
        "--no-write-target", action="store_true",
        help="只生成到 outputs/，不写入目标 ACCL 仓库",
    )
    common(p_convert)
    p_convert.set_defaults(func=cmd_convert)

    p_batch = sub.add_parser("batch", help="按清单批量迁移并产出报告")
    p_batch.add_argument("--manifest", required=True, help="批量清单 YAML（含 inputs 列表）")
    common(p_batch)
    p_batch.set_defaults(func=cmd_batch)

    p_test = sub.add_parser("test", help="为指定算子生成并执行 host/kernel 测试")
    p_test.add_argument("--input", help="原始 CCCL 文件路径（用于自动推导 target_relpath）")
    p_test.add_argument("--target-relpath", help="直接指定目标相对路径（如 asc-stl/include/asc/std/__algorithm/max.h）")
    p_test.add_argument("--quiet", action="store_true", help="减少日志输出")
    p_test.add_argument("--mock", action="store_true", help=argparse.SUPPRESS)
    p_test.add_argument("--dry-run", action="store_true", help=argparse.SUPPRESS)
    p_test.add_argument("--mock-rounds", type=int, default=0, help=argparse.SUPPRESS)
    p_test.add_argument("--require-push", action="store_true", help=argparse.SUPPRESS)
    p_test.add_argument(
        "--show-model-io",
        action="store_true",
        help="测试反馈修复时打印与模型的完整对话",
    )
    add_test_flags(p_test, include_with_tests=False)
    p_test.set_defaults(func=cmd_test)

    p_self = sub.add_parser("selftest", help="离线冒烟测试")
    p_self.set_defaults(func=cmd_selftest)

    p_inventory = sub.add_parser(
        "inventory",
        help="只读扫描真实 CCCL libcudacxx headers，并写入 deterministic JSON 报告",
    )
    p_inventory.add_argument(
        "--cccl-repo",
        help=cccl_repo_help,
    )
    p_inventory.add_argument(
        "--output",
        default="cccl_header_inventory.json",
        help="写入 outputs/ 下的报告文件名",
    )
    p_inventory.set_defaults(func=cmd_inventory)

    p_test_index = sub.add_parser(
        "test-index",
        help="只读扫描真实 CCCL libcudacxx tests，并写入 header/test mapping 报告",
    )
    p_test_index.add_argument(
        "--cccl-repo",
        help=cccl_repo_help,
    )
    p_test_index.add_argument(
        "--output",
        default="cccl_test_index.json",
        help="写入 outputs/ 下的报告文件名",
    )
    p_test_index.set_defaults(func=cmd_test_index)

    p_test_plan = sub.add_parser(
        "test-plan",
        help="Node 13：为一个 CCCL header 生成 selected/deferred 上游测试迁移计划",
    )
    p_test_plan.add_argument(
        "--entry-header",
        required=True,
        help="CCCL header relative to libcudacxx/include/cuda/std, e.g. __numeric/midpoint.h",
    )
    p_test_plan.add_argument(
        "--cccl-repo",
        help=cccl_repo_help,
    )
    p_test_plan.add_argument(
        "--max-selected-tests",
        type=int,
        default=4,
        help="最多选入 prompt 的 mapped .pass.cpp 数量",
    )
    p_test_plan.add_argument(
        "--scaffold-inexpressible",
        action="append",
        default=[],
        help="显式标记为当前 kernel scaffold 不可表达的上游测试相对路径；可重复",
    )
    p_test_plan.add_argument(
        "--output",
        help="写入 outputs/ 下的报告文件名；默认按 entry header 自动生成",
    )
    p_test_plan.set_defaults(func=cmd_test_plan)

    p_test_migrate = sub.add_parser(
        "test-migrate",
        help="Node 13：为一个已迁移 ACCL header 生成 AI host/kernel 测试 artifacts（不写测试、不运行）",
    )
    p_test_migrate.add_argument(
        "--entry-header",
        required=True,
        help="CCCL header relative to libcudacxx/include/cuda/std, e.g. __algorithm/max.h",
    )
    p_test_migrate.add_argument(
        "--cccl-repo",
        help=cccl_repo_help,
    )
    p_test_migrate.add_argument("--mock", action="store_true", help="使用 mock 模型生成测试 artifacts")
    p_test_migrate.add_argument("--real-ai", action="store_true", help="显式允许真实模型/API 调用")
    p_test_migrate.add_argument(
        "--scaffold-inexpressible",
        action="append",
        default=[],
        help="显式标记为当前 kernel scaffold 不可表达的上游测试相对路径；可重复",
    )
    p_test_migrate.add_argument(
        "--output",
        default="test_migration_artifacts.json",
        help="写入 outputs/ 下的 artifacts 报告文件名",
    )
    p_test_migrate.add_argument("--quiet", action="store_true", help="减少日志输出")
    p_test_migrate.add_argument(
        "--show-model-io",
        action="store_true",
        help="真实模型调用时打印与模型的完整对话",
    )
    p_test_migrate.set_defaults(func=cmd_test_migrate)

    p_dep_graph = sub.add_parser(
        "dep-graph",
        help="只读扫描真实 CCCL libcudacxx headers，并写入 include dependency graph 报告",
    )
    p_dep_graph.add_argument(
        "--cccl-repo",
        help=cccl_repo_help,
    )
    p_dep_graph.add_argument(
        "--output",
        default="cccl_dep_graph.json",
        help="写入 outputs/ 下的报告文件名",
    )
    p_dep_graph.set_defaults(func=cmd_dep_graph)

    p_revalidate = sub.add_parser(
        "revalidate-samples",
        help="只读参考真实 CCCL，汇总 Node 6 既有样本的 header/test 映射证据",
    )
    p_revalidate.add_argument(
        "--cccl-repo",
        help=cccl_repo_help,
    )
    p_revalidate.add_argument(
        "--output",
        default="sample_revalidation.json",
        help="写入 outputs/ 下的报告文件名",
    )
    p_revalidate.set_defaults(func=cmd_revalidate_samples)

    p_status = sub.add_parser(
        "migration-status",
        help="生成 Node 9 machine-readable migration status JSON 报告",
    )
    p_status.add_argument(
        "--cccl-repo",
        help=cccl_repo_help,
    )
    p_status.add_argument(
        "--output",
        default="migration_status.json",
        help="写入 outputs/ 下的报告文件名",
    )
    p_status.set_defaults(func=cmd_migration_status)

    p_context = sub.add_parser(
        "migration-context",
        help="生成 Node 11 bounded AI migration context pack JSON",
    )
    p_context.add_argument(
        "--entry-header",
        required=True,
        help="CCCL header relative to libcudacxx/include/cuda/std, e.g. __algorithm/all_of.h",
    )
    p_context.add_argument(
        "--cccl-repo",
        help=cccl_repo_help,
    )
    p_context.add_argument(
        "--output",
        help="写入 outputs/ 下的报告文件名；默认按 entry header 自动生成",
    )
    p_context.set_defaults(func=cmd_migration_context)

    p_folder_plan = sub.add_parser(
        "folder-plan",
        help="扫描一个 CCCL 源目录，分析依赖/复杂度并生成首批与后续迁移推荐计划",
    )
    p_folder_plan.add_argument(
        "--source-dir",
        required=True,
        help="CCCL 源目录，可为绝对路径、std/__algorithm、cuda/std/__algorithm 或 __algorithm",
    )
    p_folder_plan.add_argument(
        "--cccl-repo",
        help=cccl_repo_help,
    )
    p_folder_plan.add_argument("--mock", action="store_true", help="不调用真实模型，使用确定性启发式计划")
    p_folder_plan.add_argument("--real-ai", action="store_true", help="调用真实模型对启发式候选做分批推荐")
    p_folder_plan.add_argument("--first-batch-size", type=int, default=5, help="首批推荐数量")
    p_folder_plan.add_argument("--followup-batch-size", type=int, default=8, help="后续批次每批数量")
    p_folder_plan.add_argument("--max-ai-candidates", type=int, default=80, help="最多提交给模型的候选数量")
    p_folder_plan.add_argument("--output-json", default=DEFAULT_FOLDER_PLAN_JSON, help="写入 outputs/ 下的 JSON 文件名")
    p_folder_plan.add_argument("--output-md", default=DEFAULT_FOLDER_PLAN_MD, help="写入 outputs/ 下的 Markdown 文件名")
    p_folder_plan.add_argument("--quiet", action="store_true", help="减少日志输出")
    p_folder_plan.add_argument("--show-model-io", action="store_true", help="真实模型调用时打印规划请求与响应")
    p_folder_plan.set_defaults(func=cmd_folder_plan)

    p_folder_migrate = sub.add_parser(
        "folder-migrate",
        help="读取 folder-plan 产物，在人工确认后执行某个推荐批次的闭包迁移",
    )
    p_folder_migrate.add_argument("--plan", required=True, help="folder-plan 生成的 JSON 文件路径")
    p_folder_migrate.add_argument(
        "--batch",
        default="first",
        help="执行哪个批次：first / all / followup-1 / followup-2 / 或逗号分隔 header 列表",
    )
    p_folder_migrate.add_argument("--approve", action="store_true", help="确认已人工审阅计划，允许执行迁移")
    p_folder_migrate.add_argument(
        "--allow-external-dependencies",
        action="store_true",
        help="允许本批次迁移 source-dir 范围外的未验证/缺失依赖；默认需要人工确认后才可扩范围",
    )
    p_folder_migrate.add_argument(
        "--cccl-repo",
        help=cccl_repo_help,
    )
    p_folder_migrate.add_argument("--plan-only", action="store_true", help="只输出每个 entry 的 dependency-convert 计划")
    p_folder_migrate.add_argument("--mock", action="store_true", help="使用 mock 模型执行迁移")
    p_folder_migrate.add_argument("--real-ai", action="store_true", help="显式允许真实模型/API 调用")
    p_folder_migrate.add_argument("--no-write-target", action="store_true", help="只生成到 outputs/，不写入目标 ACCL 仓库")
    p_folder_migrate.add_argument("--limit", type=int, default=0, help="最多执行多少个 header（0=不限制）")
    p_folder_migrate.add_argument("--continue-on-error", action="store_true", help="某个 header 失败后继续执行后续 header")
    p_folder_migrate.add_argument("--quiet", action="store_true", help="减少日志输出")
    p_folder_migrate.add_argument("--show-model-io", action="store_true", help="真实模型调用时打印与模型的完整对话")
    add_test_flags(p_folder_migrate)
    p_folder_migrate.add_argument(
        "--max-fix-rounds", type=int, default=0,
        help="配合 --test-feedback-to-model：单个算子测试失败回灌模型的最大修复轮数（0=取 retry.max_fix_rounds）",
    )
    p_folder_migrate.add_argument(
        "--continue-on-test-failure",
        action="store_true",
        help="传递给 dependency-convert：测试失败时仍继续改写/测试后续算子",
    )
    p_folder_migrate.add_argument(
        "--defer-dependents-on-failure",
        action="store_true",
        help="传递给 dependency-convert：失败时只延期依赖它的下游",
    )
    p_folder_migrate.add_argument("--verify-includes", action="store_true", help="改写后做自包含 include 编译自检")
    p_folder_migrate.add_argument("--verify-includes-strict", action="store_true", help="include 自检失败计为失败")
    p_folder_migrate.set_defaults(func=cmd_folder_migrate)

    p_package_plan = sub.add_parser(
        "package-plan",
        help="对整个源 CCCL 包做依赖分析，输出严格按依赖波次分批的迁移计划（不调用模型）",
    )
    p_package_plan.add_argument(
        "--cccl-repo",
        help=cccl_repo_help,
    )
    p_package_plan.add_argument(
        "--output-json", default=DEFAULT_PACKAGE_PLAN_JSON, help="写入 outputs/ 下的 JSON 文件名（活台账）"
    )
    p_package_plan.add_argument(
        "--output-md", default=DEFAULT_PACKAGE_PLAN_MD, help="写入 outputs/ 下的 Markdown 文件名"
    )
    p_package_plan.add_argument(
        "--mark",
        default="",
        help="把这些 header（逗号分隔，相对命名空间根，如 __algorithm/clamp.h）标记为已迁移成功；持久化",
    )
    p_package_plan.add_argument(
        "--unmark",
        default="",
        help="撤销这些 header（逗号分隔）的人工已完成标记",
    )
    p_package_plan.add_argument("--quiet", action="store_true", help="减少日志输出")
    p_package_plan.set_defaults(func=cmd_package_plan)

    p_package_migrate = sub.add_parser(
        "package-migrate",
        help="读取 package-plan 产物，人工确认后按波次批次执行闭包迁移，并自动回写已完成标记",
    )
    p_package_migrate.add_argument("--plan", required=True, help="package-plan 生成的 JSON 文件路径")
    p_package_migrate.add_argument(
        "--batch",
        default="next",
        help="执行哪个批次：next（首个仍有未完成头的波次）/ all / batch-1 / batch-2 / 或逗号分隔 header 列表",
    )
    p_package_migrate.add_argument("--approve", action="store_true", help="确认已人工审阅计划，允许执行迁移")
    p_package_migrate.add_argument(
        "--cccl-repo",
        help=cccl_repo_help,
    )
    p_package_migrate.add_argument("--plan-only", action="store_true", help="只输出每个 entry 的 dependency-convert 计划")
    p_package_migrate.add_argument("--mock", action="store_true", help="使用 mock 模型执行迁移")
    p_package_migrate.add_argument("--real-ai", action="store_true", help="显式允许真实模型/API 调用")
    p_package_migrate.add_argument("--no-write-target", action="store_true", help="只生成到 outputs/，不写入目标 ACCL 仓库")
    p_package_migrate.add_argument("--limit", type=int, default=0, help="最多执行多少个 header（0=不限制）")
    p_package_migrate.add_argument("--continue-on-error", action="store_true", help="某个 header 失败后继续执行后续 header")
    p_package_migrate.add_argument("--quiet", action="store_true", help="减少日志输出")
    p_package_migrate.add_argument("--show-model-io", action="store_true", help="真实模型调用时打印与模型的完整对话")
    add_test_flags(p_package_migrate)
    p_package_migrate.add_argument(
        "--max-fix-rounds", type=int, default=0,
        help="配合 --test-feedback-to-model：单个算子测试失败回灌模型的最大修复轮数（0=取 retry.max_fix_rounds）",
    )
    p_package_migrate.add_argument(
        "--continue-on-test-failure",
        action="store_true",
        help="传递给 dependency-convert：测试失败时仍继续改写/测试后续算子",
    )
    p_package_migrate.add_argument(
        "--defer-dependents-on-failure",
        action="store_true",
        help="传递给 dependency-convert：失败时只延期依赖它的下游",
    )
    p_package_migrate.add_argument("--verify-includes", action="store_true", help="改写后做自包含 include 编译自检")
    p_package_migrate.add_argument("--verify-includes-strict", action="store_true", help="include 自检失败计为失败")
    p_package_migrate.set_defaults(func=cmd_package_migrate)

    p_dep_convert = sub.add_parser(
        "dependency-convert",
        help="Node 12：按依赖闭包 leaf-first 迁移一个 CCCL header",
    )
    p_dep_convert.add_argument(
        "--entry-header",
        required=True,
        help="CCCL header relative to libcudacxx/include/cuda/std, e.g. __algorithm/all_of.h",
    )
    p_dep_convert.add_argument(
        "--cccl-repo",
        help=cccl_repo_help,
    )
    p_dep_convert.add_argument(
        "--plan-only",
        action="store_true",
        help="只输出 leaf-first 计划，不调用模型也不写入 ACCL",
    )
    p_dep_convert.add_argument("--mock", action="store_true", help="使用 mock 模型执行 dependency rewrite")
    p_dep_convert.add_argument("--real-ai", action="store_true", help="显式允许真实模型/API 调用")
    p_dep_convert.add_argument(
        "--no-write-target",
        action="store_true",
        help="实际 rewrite 时只生成到 outputs/，不写入目标 ACCL 仓库",
    )
    p_dep_convert.add_argument(
        "--output",
        default="dependency_convert_report.json",
        help="写入 outputs/ 下的报告文件名",
    )
    p_dep_convert.add_argument("--quiet", action="store_true", help="减少日志输出")
    p_dep_convert.add_argument(
        "--show-model-io",
        action="store_true",
        help="实际 rewrite 时打印与模型的完整对话",
    )
    # 闭包改写后逐个算子跑 host/kernel 测试（leaf-first，紧跟每次 rewrite）。
    add_test_flags(p_dep_convert)
    p_dep_convert.add_argument(
        "--max-fix-rounds", type=int, default=0,
        help="配合 --test-feedback-to-model：单个算子测试失败回灌模型的最大修复轮数（0=取 retry.max_fix_rounds）",
    )
    p_dep_convert.add_argument(
        "--continue-on-test-failure",
        action="store_true",
        help="某算子 host/kernel 测试失败时仍继续改写/测试后续算子（默认失败即停）",
    )
    p_dep_convert.add_argument(
        "--defer-dependents-on-failure",
        action="store_true",
        help="某算子失败时只延期「真正依赖它」的下游，独立分支继续迁移（局部可用、整体延期）",
    )
    p_dep_convert.add_argument(
        "--verify-includes",
        action="store_true",
        help="每个算子改写后做一次自包含 include 编译自检（g++ -fsyntax-only），结果写入报告",
    )
    p_dep_convert.add_argument(
        "--verify-includes-strict",
        action="store_true",
        help="配合 --verify-includes：include 不自包含（缺依赖）按失败处理，参与 defer/stop 逻辑",
    )
    p_dep_convert.set_defaults(func=cmd_dependency_convert)

    p_mk = sub.add_parser(
        "make-example", help="把已迁移并验证的算子晋升为 examples/ 金标准 few-shot 示例"
    )
    p_mk.add_argument("operators", nargs="*", help="算子名（如 clamp minmax sort3）；留空且不加 --all 时列出候选")
    p_mk.add_argument("--all", action="store_true", help="晋升目标仓里全部已迁移算子")
    p_mk.add_argument("--overwrite", action="store_true", help="覆盖 examples/ 里已存在的同名示例")
    p_mk.add_argument("--headers-only", action="store_true", help="只晋升头对，不带测试三元组")
    p_mk.add_argument("--no-validate", action="store_true", help="跳过质量门禁（不建议）")
    p_mk.set_defaults(func=cmd_make_example)

    return parser
