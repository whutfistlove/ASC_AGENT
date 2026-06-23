"""CLI command implementations (one ``cmd_*`` per sub-command) and their
command-local helpers. Shared helpers live in :mod:`cli.helpers`.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

from cli.helpers import (
    DEFAULT_LEDGER_PATH,
    DEFAULT_SETTINGS,
    PROJECT_ROOT,
    _build_status_report_with_state,
    _build_test_feedback_text,
    _cli_cccl_repo,
    _format_attempt_history,
    _generate_model_fix_from_test_feedback,
    _host_test_file_for,
    _is_env_blocked,
    _maybe_build_toolbox,
    _maybe_migrate_tests,
    _mode_label,
    _model_label,
    _record_migration_state,
    _resolve_target_relpath_for_test,
    _resolve_test_selection,
    _run_operator_tests,
    _state_status_map,
    _tests_all_passed,
    make_components,
    print_batch_table,
    write_batch_report,
    write_dependency_convert_report,
)
from core.analysis.dep_graph import scan_dependency_graph, write_dependency_graph_report
from core.analysis.inventory import scan_header_inventory, write_inventory_report
from core.analysis.migration_context import (
    build_migration_context_pack_from_scans,
    default_context_pack_filename,
    write_migration_context_pack,
)
from core.analysis.migration_status import (
    scan_migration_status,
    target_relpath_for_header,
    write_migration_status_report,
)
from core.analysis.path_mapper import expected_guard_from_relpath
from core.analysis.test_index import scan_test_index, write_test_index_report
from core.common.config import Config
from core.common.utils import save_text
from core.llm.model_client import MockModelClient, build_model_client
from core.migration.example_promote import discover_promotable, promote_operator
from core.migration.fix_once import run_test_artifact_fix
from core.migration.pipeline import FakeVerifier, Pipeline, RunResult
from core.planning.folder_planner import (
    FolderPlanOptions,
    build_folder_plan_payload,
    refine_folder_plan_with_model,
    write_folder_plan,
)
from core.planning.package_planner import (
    build_package_plan_payload,
    headers_for_batch,
    load_package_plan,
    plan_completed_set,
    read_manual_marks,
    write_package_plan,
)
from core.testing.operator_test import OperatorTestRunner
from core.testing.sample_revalidation import build_sample_revalidation_report, write_sample_revalidation_report
from core.testing.test_migrator import (
    default_test_plan_filename,
    migrate_operator_tests,
    plan_upstream_tests_for_header,
    write_upstream_test_plan_report,
)


def cmd_run(args) -> int:
    settings_path = Path(args.settings) if args.settings else DEFAULT_SETTINGS
    config, model_client, verifier = make_components(
        mock=args.mock, dry_run=args.dry_run, verbose=not args.quiet,
        settings_path=settings_path, rounds_to_pass=args.mock_rounds,
    )
    pipeline = Pipeline(config, model_client, verifier, verbose=not args.quiet,
                        show_model_io=getattr(args, "show_model_io", False),
                        toolbox=_maybe_build_toolbox(config))
    result = pipeline.run(Path(args.input))

    if args.with_tests:
        artifacts = None
        if result.commit_passed:
            artifacts = _maybe_migrate_tests(
                args, config, model_client,
                input_path=args.input, target_relpath=result.target_relpath, verbose=not args.quiet,
            )
        result.test_result = _run_operator_tests(
            args,
            config,
            result.target_relpath,
            require_ready_commit=True,
            commit_passed=result.commit_passed,
            test_artifacts=artifacts,
        )
        run_host, run_kernel = _resolve_test_selection(args)
        if (
            args.test_feedback_to_model
            and not args.prepare_tests_only
            and not _tests_all_passed(result.test_result, run_host, run_kernel, test_dry_run=args.test_dry_run)
            and not result.test_result.get("skipped")
            and not _is_env_blocked(result.test_result)
        ):
            result.test_result["model_feedback_fix"] = _generate_model_fix_from_test_feedback(
                args=args,
                config=config,
                model_client=model_client,
                target_relpath=result.target_relpath,
                expected_header_guard=result.expected_header_guard,
                test_result=result.test_result,
                rounds_used=result.rounds_used,
            )

    print("\n=== 运行结果 ===")
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    if args.require_push and not result.pushed:
        return 2

    if args.with_tests:
        run_host, run_kernel = _resolve_test_selection(args)
        if not args.prepare_tests_only and not _tests_all_passed(
            result.test_result, run_host, run_kernel, test_dry_run=args.test_dry_run
        ):
            return 2
    return 0


def _run_convert_test_loop(args, config: Config, model_client, result, write_to_repo: bool) -> dict:
    """convert 的「测试 → 失败回传模型 → 改正写回 → 重测」全自动迭代闭环。

    - 未加 --test-feedback-to-model：只测一次，不修复（保持单趟行为）。
    - 加了 --test-feedback-to-model（真实、非 dry-run/prepare/mock）：失败则进入循环，
      每轮把 host/kernel 日志 + 当前仓库代码回传模型，写回修复版后重测，
      直到通过或达到最大轮数（--max-fix-rounds，缺省取 retry.max_fix_rounds）。
    """
    run_host, run_kernel = _resolve_test_selection(args)

    # 迁移测试（host + kernel_spec）；不可用则回退内置模板。
    artifacts = _maybe_migrate_tests(
        args, config, model_client,
        input_path=getattr(args, "input", None), target_relpath=result.target_relpath,
        verbose=not args.quiet,
    )

    # 第一次测试（带迁移好的测试 artifacts）
    test_result = _run_operator_tests(
        args, config, result.target_relpath,
        require_ready_commit=False, commit_passed=True, skip_in_mock=False,
        test_artifacts=artifacts,
    )

    # 是否需要进入修复循环
    if (
        not args.test_feedback_to_model
        or args.prepare_tests_only
        or args.test_dry_run
        or args.mock
        or test_result.get("skipped")
        or test_result.get("error")
    ):
        return test_result
    if _tests_all_passed(test_result, run_host, run_kernel, test_dry_run=args.test_dry_run):
        return test_result
    # 环境类失败：改代码无用，直接终止循环并明确标注（P0 止血）。
    if _is_env_blocked(test_result):
        test_result["fix_loop_skipped"] = (
            "测试失败被判定为环境问题（如旧 CMake 缓存 / 缺 llvm-objdump / 缺驱动库 / 无 cannsim），"
            "改代码无济于事，已跳过模型修复循环。请先修复环境后重试。"
        )
        return test_result
    if not write_to_repo:
        test_result["fix_loop_skipped"] = "需写回仓库才能闭环修复，请去掉 --no-write-target"
        return test_result

    target_file = Path(config.target_repo) / result.target_relpath
    host_file = _host_test_file_for(config, result.target_relpath)
    max_rounds = getattr(args, "max_fix_rounds", 0) or config.max_fix_rounds
    rounds_log: list[dict] = []
    # 当前可修复件：header(写在仓库) + host 测试 + kernel_spec（保存在内存里随轮更新）。
    cur_artifacts: dict = dict(artifacts) if artifacts else {}
    last_signature = None  # 上一轮回传模型的输入签名，用于去重早停
    toolbox = _maybe_build_toolbox(config)  # P1：启用后模型可取证/自检（默认关闭）

    for r in range(1, max_rounds + 1):
        if not args.quiet:
            print(f"\n==== 测试反馈修复 第 {r}/{max_rounds} 轮 ====")
        test_text = _build_test_feedback_text(test_result)
        if not test_text:
            test_result["fix_loop_note"] = "测试反馈为空，停止修复"
            break

        header_text = target_file.read_text(encoding="utf-8")
        if host_file.exists():
            host_text = host_file.read_text(encoding="utf-8")
        else:
            host_text = cur_artifacts.get("host_test_code", "") or ""

        # 去重早停：若本轮回传模型的输入与上一轮完全相同，模型只会给出相同结果，
        # 继续调用纯属浪费（sort3 三轮 fix_request 字节相同即此症）。
        signature = (header_text, host_text, json.dumps(cur_artifacts.get("kernel_spec"), sort_keys=True), test_text)
        if signature == last_signature:
            test_result["fix_loop_note"] = "本轮输入与上一轮相同，无新信息，停止修复（去重早停）。"
            break
        last_signature = signature

        try:
            # 关键：失败时模型可改 header / host 测试 / kernel_spec 任意子集；
            # 算子语义为基准，测试写错就改测试，绝不为迁就测试而篡改算子（如 swap）。
            fix = run_test_artifact_fix(
                config=config,
                model_client=model_client,
                target_relpath=result.target_relpath,
                expected_header_guard=result.expected_header_guard,
                header_text=header_text,
                host_test_text=host_text,
                kernel_spec=cur_artifacts.get("kernel_spec"),
                test_feedback_text=test_text,
                round_index=r,
                attempt_history=_format_attempt_history(rounds_log),  # 跨轮记忆
                verbose=not args.quiet,
                show_model_io=getattr(args, "show_model_io", False),
                toolbox=toolbox,
                max_tool_rounds=config.model_max_tool_rounds,
            )
        except Exception as exc:  # 单轮模型/解析失败不应让整个流程崩
            rounds_log.append({"round": r, "error": f"{type(exc).__name__}: {exc}"})
            test_result["fix_rounds"] = rounds_log
            break

        applied: list[str] = []
        if fix.get("header_code"):
            target_file.write_text(fix["header_code"], encoding="utf-8")
            applied.append("header")
        if fix.get("host_test_code"):
            cur_artifacts["host_test_code"] = fix["host_test_code"]
            applied.append("host_test")
        if fix.get("kernel_spec"):
            cur_artifacts["kernel_spec"] = fix["kernel_spec"]
            applied.append("kernel_spec")

        # 模型没给出任何可改动件：再测也是原样，直接停止（避免空转）。
        if not applied:
            rounds_log.append({
                "round": r, "root_cause": fix.get("root_cause", ""), "applied": [],
                "note": "模型未返回任何可改动件，停止修复",
            })
            result.rounds_used = r
            break

        # 用最新 artifacts 重新生成测试并重测
        test_result = _run_operator_tests(
            args, config, result.target_relpath,
            require_ready_commit=False, commit_passed=True, skip_in_mock=False,
            test_artifacts=cur_artifacts,
        )
        passed = _tests_all_passed(test_result, run_host, run_kernel, test_dry_run=args.test_dry_run)
        rounds_log.append({
            "round": r,
            "root_cause": fix.get("root_cause", ""),
            "applied": applied,
            "host_passed": test_result.get("host_passed"),
            "kernel_passed": test_result.get("kernel_passed"),
            "passed": passed,
            "test_error": test_result.get("error", ""),
        })
        result.rounds_used = r
        if passed or test_result.get("error"):
            break
        # 改完代码后若失败转为环境类问题，继续改代码也无用，停止。
        if _is_env_blocked(test_result):
            test_result["fix_loop_note"] = "本轮修复后失败转为环境问题，停止修复。"
            break

    test_result["fix_rounds"] = rounds_log
    return test_result


def cmd_convert(args) -> int:
    """只做「生成 -> 写入目标仓库 -> （可选）跑测试 + 自动闭环修复」，跳过 git 提交/推送。

    对应「提交暂时忽略」的全流程，是单项目内打通生成到测试的主入口。
    """
    settings_path = Path(args.settings) if args.settings else DEFAULT_SETTINGS
    overrides = {"model": {"provider": "mock"}} if args.mock else None
    config = Config.load(settings_path, PROJECT_ROOT, overrides=overrides)
    model_client = MockModelClient() if args.mock else build_model_client(config)

    # convert 不经过 git，verifier 用 None 占位即可。
    pipeline = Pipeline(config, model_client, verifier=None, verbose=not args.quiet,
                        show_model_io=getattr(args, "show_model_io", False),
                        toolbox=_maybe_build_toolbox(config))
    write_to_repo = not args.no_write_target
    result = pipeline.convert_only(Path(args.input), write_to_repo=write_to_repo)

    if args.with_tests and not result.error:
        # mock 生成的是占位头文件，无法真正编译；自动降级为仅生成脚手架。
        if args.mock and not args.prepare_tests_only and not args.test_dry_run:
            print("[convert] mock 模式：自动切换为 --prepare-tests-only（mock 头文件无法编译）")
            args.prepare_tests_only = True
        # 测试 → 失败回传模型 → 改正写回 → 重测 的全自动闭环
        result.test_result = _run_convert_test_loop(args, config, model_client, result, write_to_repo)
        # 把确定的通过结论回写 migration_state（闭合 能测 → 能扩：下次闭包可跳过已验证且未变的头）。
        _run_host, _run_kernel = _resolve_test_selection(args)
        _record_migration_state(
            config, input_path=getattr(args, "input", None),
            target_relpath=result.target_relpath, test_result=result.test_result,
            run_host=_run_host, run_kernel=_run_kernel, args=args,
        )

    print("\n=== 转换结果 ===")
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))

    if result.error:
        return 2
    if args.with_tests and not args.prepare_tests_only:
        run_host, run_kernel = _resolve_test_selection(args)
        if not _tests_all_passed(result.test_result or {}, run_host, run_kernel, test_dry_run=args.test_dry_run):
            return 2
    return 0


def _load_manifest(manifest_path: Path) -> list[str]:
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    inputs = data.get("inputs", [])
    if not isinstance(inputs, list) or not inputs:
        raise ValueError("manifest 需包含非空的 inputs 列表")
    return [str(p) for p in inputs]


def cmd_batch(args) -> int:
    settings_path = Path(args.settings) if args.settings else DEFAULT_SETTINGS
    inputs = _load_manifest(Path(args.manifest))

    config, model_client, verifier = make_components(
        mock=args.mock, dry_run=args.dry_run, verbose=not args.quiet,
        settings_path=settings_path, rounds_to_pass=args.mock_rounds,
    )

    results: list[RunResult] = []
    for idx, item in enumerate(inputs, 1):
        print(f"\n############ [{idx}/{len(inputs)}] {item} ############")
        # 每个文件用独立的 mock client（避免脚本化响应跨文件串扰）
        if args.mock:
            model_client = MockModelClient()
            verifier = FakeVerifier(config, rounds_to_pass=args.mock_rounds, verbose=not args.quiet)
        pipeline = Pipeline(config, model_client, verifier, verbose=not args.quiet,
                            show_model_io=getattr(args, "show_model_io", False),
                            toolbox=_maybe_build_toolbox(config))
        one = pipeline.run(Path(item))
        if args.with_tests:
            artifacts = None
            if one.commit_passed:
                artifacts = _maybe_migrate_tests(
                    args, config, model_client,
                    input_path=item, target_relpath=one.target_relpath, verbose=not args.quiet,
                )
            one.test_result = _run_operator_tests(
                args,
                config,
                one.target_relpath,
                require_ready_commit=True,
                commit_passed=one.commit_passed,
                test_artifacts=artifacts,
            )
            run_host, run_kernel = _resolve_test_selection(args)
            if (
                args.test_feedback_to_model
                and not args.prepare_tests_only
                and not _tests_all_passed(one.test_result, run_host, run_kernel, test_dry_run=args.test_dry_run)
                and not one.test_result.get("skipped")
                and not _is_env_blocked(one.test_result)
            ):
                one.test_result["model_feedback_fix"] = _generate_model_fix_from_test_feedback(
                    args=args,
                    config=config,
                    model_client=model_client,
                    target_relpath=one.target_relpath,
                    expected_header_guard=one.expected_header_guard,
                    test_result=one.test_result,
                    rounds_used=one.rounds_used,
                )
        results.append(one)

    print_batch_table(results)
    report_path = write_batch_report(config, results)
    print(f"\n报告已写入: {report_path}")

    if args.require_push and any(not r.pushed for r in results):
        return 2
    if args.with_tests:
        run_host, run_kernel = _resolve_test_selection(args)
        if not args.prepare_tests_only:
            for r in results:
                if not _tests_all_passed(r.test_result or {}, run_host, run_kernel, test_dry_run=args.test_dry_run):
                    return 2
    return 0


def cmd_test(args) -> int:
    settings_path = Path(args.settings) if args.settings else DEFAULT_SETTINGS
    config = Config.load(settings_path, PROJECT_ROOT)
    target_relpath = _resolve_target_relpath_for_test(args, config)
    input_path = getattr(args, "input", None)

    test_migration_model_client = None
    if input_path and not args.mock and not args.test_dry_run:
        test_migration_model_client = build_model_client(config)

    feedback_model_client = test_migration_model_client
    if args.test_feedback_to_model and feedback_model_client is None:
        feedback_model_client = MockModelClient() if args.mock else build_model_client(config)

    # 有真实模型且给了 --input 时，迁移该算子的测试（host + kernel_spec）。
    artifacts = _maybe_migrate_tests(
        args, config, test_migration_model_client,
        input_path=input_path, target_relpath=target_relpath, verbose=not args.quiet,
    )

    result = _run_operator_tests(
        args,
        config,
        target_relpath,
        require_ready_commit=False,
        commit_passed=True,
        test_artifacts=artifacts,
    )

    print("\n=== 测试结果 ===")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if result.get("error"):
        return 2
    run_host, run_kernel = _resolve_test_selection(args)
    if (
        args.test_feedback_to_model
        and not args.prepare_tests_only
        and not _tests_all_passed(result, run_host, run_kernel, test_dry_run=args.test_dry_run)
        and not result.get("skipped")
        and not _is_env_blocked(result)
    ):
        result["model_feedback_fix"] = _generate_model_fix_from_test_feedback(
            args=args,
            config=config,
            model_client=feedback_model_client,
            target_relpath=target_relpath,
            expected_header_guard=expected_guard_from_relpath(target_relpath),
            test_result=result,
            rounds_used=0,
        )
        print("\n=== 测试反馈修复稿 ===")
        print(json.dumps(result["model_feedback_fix"], ensure_ascii=False, indent=2))

    if args.prepare_tests_only:
        return 0
    return 0 if _tests_all_passed(result, run_host, run_kernel, test_dry_run=args.test_dry_run) else 2


def cmd_make_example(args) -> int:
    """把已迁移并验证的算子晋升为 examples/ 金标准 few-shot 示例（curation 步骤）。"""
    settings_path = Path(args.settings) if args.settings else DEFAULT_SETTINGS
    config = Config.load(settings_path, PROJECT_ROOT)

    names = list(args.operators or [])
    if args.all:
        names = discover_promotable(config)
        if not names:
            print("没有可晋升的算子（目标仓尚无已迁移的 ACCL 头）。")
            return 1
    if not names:
        print("请指定算子名，或用 --all 晋升全部已迁移算子。可晋升候选：")
        for n in discover_promotable(config):
            print(f"  - {n}")
        return 2

    ok = 0
    for name in names:
        try:
            r = promote_operator(
                config, name, overwrite=args.overwrite,
                validate=not args.no_validate, include_test=not args.headers_only,
            )
            ok += 1
            tag_h = "头✓" if r["header_written"] else "头(跳过)"
            tag_t = "—" if args.headers_only else ("测试✓" if r["test_written"] else "测试(跳过)")
            extra = f"  [{'; '.join(r['skipped'])}]" if r["skipped"] else ""
            print(f"[promote] {name}（{r['module']}）-> examples/  {tag_h} {tag_t}{extra}")
        except Exception as exc:
            print(f"[skip] {name}: {type(exc).__name__}: {exc}")
    print(f"\n完成：{ok}/{len(names)} 个算子已晋升为示例。")
    return 0 if ok else 1


def cmd_selftest(args) -> int:
    """用内置 repo 样本做离线冒烟，验证整条链路在 mock 下可收敛。"""
    manifest = PROJECT_ROOT / "tests" / "data" / "manifest.yaml"
    print("== selftest（mock，离线） ==")
    ns = argparse.Namespace(
        manifest=str(manifest), settings=None, mock=True, dry_run=False,
        quiet=True, mock_rounds=2, require_push=True,
        with_tests=False, host_only=False, kernel_only=False,
        kernel_mode="run_test", prepare_tests_only=False,
        overwrite_tests=False, test_dry_run=False,
        kernel_fast=False, kernel_timeout=0, kernel_print_samples=None,
        test_feedback_to_model=False, test_feedback_skill="rewrite_fix_from_log_and_test.md",
    )
    return cmd_batch(ns)


def cmd_inventory(args) -> int:
    """Scan real CCCL libcudacxx headers and write a deterministic JSON report."""
    settings_path = Path(args.settings) if args.settings else DEFAULT_SETTINGS
    config = Config.load(settings_path, PROJECT_ROOT)
    cccl_repo = _cli_cccl_repo(config, args)
    report = scan_header_inventory(cccl_repo, include_root_rel=config.source_repo_prefix, symbol_dependency_rules=config.symbol_dependency_rules)
    report_path = write_inventory_report(report, config.output_dir, filename=args.output)
    summary = report.summary()
    print("== CCCL header inventory ==")
    print(f"cccl_repo: {report.cccl_repo}")
    print(f"header_root: {report.header_root}")
    print(f"headers: {summary['header_count']}")
    print(f"report: {report_path}")
    return 0


def cmd_test_index(args) -> int:
    """Scan real CCCL libcudacxx tests and write a deterministic JSON report."""
    settings_path = Path(args.settings) if args.settings else DEFAULT_SETTINGS
    config = Config.load(settings_path, PROJECT_ROOT)
    cccl_repo = _cli_cccl_repo(config, args)
    report = scan_test_index(cccl_repo, include_root_rel=config.source_repo_prefix, test_root_rel=config.cccl_test_prefix)
    report_path = write_test_index_report(report, config.output_dir, filename=args.output)
    summary = report.summary()
    print("== CCCL libcudacxx test index ==")
    print(f"cccl_repo: {report.cccl_repo}")
    print(f"test_root: {report.test_root}")
    print(f"tests: {summary['test_count']}")
    print(f"helper_headers: {summary['helper_header_count']}")
    print(f"mapped_headers: {summary['mapped_header_count']}")
    print(f"unmapped_headers: {summary['unmapped_header_count']}")
    print(f"unmapped_tests: {summary['unmapped_test_count']}")
    print(f"report: {report_path}")
    return 0


def cmd_test_plan(args) -> int:
    """Write a Node 13 selected/deferred upstream test plan for one header."""
    settings_path = Path(args.settings) if args.settings else DEFAULT_SETTINGS
    config = Config.load(settings_path, PROJECT_ROOT)
    cccl_repo = _cli_cccl_repo(config, args)
    inventory = scan_header_inventory(cccl_repo, include_root_rel=config.source_repo_prefix, symbol_dependency_rules=config.symbol_dependency_rules)
    test_index = scan_test_index(cccl_repo, include_root_rel=config.source_repo_prefix, test_root_rel=config.cccl_test_prefix)
    dep_graph = scan_dependency_graph(cccl_repo, include_root_rel=config.source_repo_prefix, symbol_dependency_rules=config.symbol_dependency_rules)
    status_report = _build_status_report_with_state(config, inventory, test_index, dep_graph)
    status_by_header = {entry.source_header: entry.status for entry in status_report.headers}
    plan = plan_upstream_tests_for_header(
        test_index,
        entry_header=args.entry_header,
        dependency_status_by_header=status_by_header,
        scaffold_inexpressible_tests=set(args.scaffold_inexpressible or []),
        max_selected_tests=args.max_selected_tests,
    )
    output = args.output or default_test_plan_filename(args.entry_header)
    report_path = write_upstream_test_plan_report(plan, config.output_dir, filename=output)
    summary = plan.summary()
    print("== Node 13 upstream test migration plan ==")
    print(f"entry_header: {plan.entry_header}")
    print(f"selected_tests: {summary['selected_count']}")
    print(f"deferred_tests: {summary['deferred_count']}")
    print("deferred_reason_counts:")
    for reason, count in summary["deferred_reason_counts"].items():
        print(f"  {reason}: {count}")
    print(f"report: {report_path}")
    return 0


def _mock_test_migration_payload(include_path: str) -> dict:
    """Small valid test-migration payload for offline `test-migrate --mock` smoke runs."""
    return {
        "host_test_code": (
            f'#include "{include_path}"\n'
            "static int g_failures = 0;\n"
            "int main(){ return g_failures == 0 ? 0 : 1; }\n"
        ),
        "kernel_spec": {
            "dtype": "float",
            "gm_inputs": 2,
            "gm_outputs": 1,
            "input_init": "h_x[i] = static_cast<float>(i); h_y[i] = static_cast<float>(i + 1);",
            "element_op_code": "z_val = x_val;",
            "golden_code": "expected = x_ref;",
        },
        "notes": "mock test migration payload; validates orchestration only",
    }


def _write_test_migration_artifact_report(
    config: Config,
    artifacts,
    *,
    output: str,
) -> Path:
    name = Path(output)
    if name.is_absolute() or len(name.parts) != 1:
        raise ValueError("test migration artifact filename must be a file name under outputs/")
    payload = {
        "algo_name": artifacts.algo_name,
        "host_test_code": artifacts.host_test_code,
        "kernel_spec": artifacts.kernel_spec,
        "notes": artifacts.notes,
        "upstream_test_plan": (
            artifacts.upstream_test_plan.to_dict()
            if artifacts.upstream_test_plan is not None
            else None
        ),
    }
    path = config.output_dir / name
    save_text(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return path


def cmd_test_migrate(args) -> int:
    """Generate Node 13 AI test artifacts for one header without writing/running tests."""
    if args.mock and args.real_ai:
        print("error: --mock and --real-ai are mutually exclusive", file=sys.stderr)
        return 2
    if not (args.mock or args.real_ai):
        print("error: choose --mock or --real-ai explicitly", file=sys.stderr)
        return 2

    settings_path = Path(args.settings) if args.settings else DEFAULT_SETTINGS
    overrides = {"model": {"provider": "mock"}} if args.mock else None
    config = Config.load(settings_path, PROJECT_ROOT, overrides=overrides)

    cccl_repo = _cli_cccl_repo(config, args)
    inventory = scan_header_inventory(cccl_repo, include_root_rel=config.source_repo_prefix, symbol_dependency_rules=config.symbol_dependency_rules)
    test_index = scan_test_index(cccl_repo, include_root_rel=config.source_repo_prefix, test_root_rel=config.cccl_test_prefix)
    dep_graph = scan_dependency_graph(cccl_repo, include_root_rel=config.source_repo_prefix, symbol_dependency_rules=config.symbol_dependency_rules)
    status_report = _build_status_report_with_state(config, inventory, test_index, dep_graph)
    status_by_header = {entry.source_header: entry.status for entry in status_report.headers}

    source_path = Path(inventory.header_root) / args.entry_header
    if not source_path.exists():
        print(f"error: source header not found: {source_path}", file=sys.stderr)
        return 2
    target_relpath = target_relpath_for_header(
        args.entry_header,
        target_repo_prefix=config.target_repo_prefix,
        segment_substitutions=config.segment_substitutions,
    )
    target_path = Path(config.target_repo) / target_relpath
    if not target_path.exists():
        print(f"error: ACCL target header not found: {target_path}", file=sys.stderr)
        return 2
    include_path = OperatorTestRunner.include_path_from_target_relpath(target_relpath)
    algo_name = OperatorTestRunner.algo_name_from_target_relpath(target_relpath)

    model_client = (
        MockModelClient(responses=[json.dumps(_mock_test_migration_payload(include_path))])
        if args.mock
        else build_model_client(config)
    )
    artifacts = migrate_operator_tests(
        config,
        model_client,
        algo_name=algo_name,
        include_path=include_path,
        target_relpath=target_relpath,
        cccl_header_text=source_path.read_text(encoding="utf-8", errors="replace"),
        accl_header_text=target_path.read_text(encoding="utf-8", errors="replace"),
        cccl_test_text="",
        test_index=test_index,
        entry_header=args.entry_header,
        dependency_status_by_header=status_by_header,
        scaffold_inexpressible_tests=set(args.scaffold_inexpressible or []),
        verbose=not args.quiet,
        show_model_io=getattr(args, "show_model_io", False),
        toolbox=None if args.mock else _maybe_build_toolbox(config),
        max_tool_rounds=config.model_max_tool_rounds,
    )
    report_path = _write_test_migration_artifact_report(config, artifacts, output=args.output)
    plan_summary = artifacts.upstream_test_plan.summary() if artifacts.upstream_test_plan else {}
    print("== Node 13 AI test migration artifacts ==")
    print(f"entry_header: {args.entry_header}")
    print(f"mode: {_mode_label(mock=args.mock, real_ai=args.real_ai)}")
    print(f"model: {_model_label(config)}")
    print(f"selected_tests: {plan_summary.get('selected_count', 0)}")
    print(f"deferred_tests: {plan_summary.get('deferred_count', 0)}")
    print(f"has_host: {artifacts.has_host()}")
    print(f"has_kernel: {artifacts.has_kernel()}")
    print(f"report: {report_path}")
    return 0


def cmd_dep_graph(args) -> int:
    """Scan CCCL headers and write a deterministic dependency graph report."""
    settings_path = Path(args.settings) if args.settings else DEFAULT_SETTINGS
    config = Config.load(settings_path, PROJECT_ROOT)
    cccl_repo = _cli_cccl_repo(config, args)
    report = scan_dependency_graph(cccl_repo, include_root_rel=config.source_repo_prefix, symbol_dependency_rules=config.symbol_dependency_rules)
    report_path = write_dependency_graph_report(report, config.output_dir, filename=args.output)
    summary = report.summary()
    print("== CCCL libcudacxx dependency graph ==")
    print(f"cccl_repo: {report.cccl_repo}")
    print(f"header_root: {report.header_root}")
    print(f"headers: {summary['header_count']}")
    print(f"edges: {summary['edge_count']}")
    print(f"symbol_dependency_edges: {summary['symbol_dependency_edge_count']}")
    print(f"cycles: {summary['cycle_count']}")
    print(f"unknown_cuda_std_includes: {summary['unknown_cuda_std_include_count']}")
    print(f"report: {report_path}")
    return 0


def cmd_revalidate_samples(args) -> int:
    """Write the Node 6 real-upstream sample revalidation report."""
    settings_path = Path(args.settings) if args.settings else DEFAULT_SETTINGS
    config = Config.load(settings_path, PROJECT_ROOT)
    cccl_repo = _cli_cccl_repo(config, args)
    report = build_sample_revalidation_report(
        cccl_repo,
        target_repo=config.target_repo,
        symbol_dependency_rules=config.symbol_dependency_rules,
    )
    report_path = write_sample_revalidation_report(report, config.output_dir, filename=args.output)
    summary = report["summary"]
    print("== Node 6 sample revalidation ==")
    print(f"cccl_repo: {report['cccl_repo']}")
    print(f"test_root: {report['test_root']}")
    print(f"samples: {summary['sample_count']}")
    print(f"mapped_samples: {summary['mapped_sample_count']}")
    for sample in report["samples"]:
        print(
            f"- {sample['name']}: {sample['status']}, "
            f"header={sample['upstream_header']}, tests={len(sample['candidate_tests'])}, "
            f"target_exists={sample['target_header_exists']}, host={sample['host_test_exists']}, "
            f"kernel_spec={sample['kernel_spec_exists']}"
        )
    print(f"report: {report_path}")
    return 0


def cmd_migration_status(args) -> int:
    """Write the Node 9 machine-readable migration status report."""
    settings_path = Path(args.settings) if args.settings else DEFAULT_SETTINGS
    config = Config.load(settings_path, PROJECT_ROOT)
    cccl_repo = _cli_cccl_repo(config, args)
    report = scan_migration_status(
        cccl_repo,
        target_repo=config.target_repo,
        ledger_path=PROJECT_ROOT / "docs" / "migration_ledger.md",
        target_repo_prefix=config.target_repo_prefix,
        segment_substitutions=config.segment_substitutions,
        symbol_dependency_rules=config.symbol_dependency_rules,
        include_root_rel=config.source_repo_prefix,
        test_root_rel=config.cccl_test_prefix,
    )
    report_path = write_migration_status_report(report, config.output_dir, filename=args.output)
    summary = report.summary()
    print("== CCCL -> ACCL migration status ==")
    print(f"cccl_repo: {report.cccl_repo}")
    print(f"target_repo: {report.target_repo}")
    print(f"headers: {summary['header_count']}")
    print(f"migrated_headers: {summary['migrated_header_count']}")
    print(f"target_only_headers: {summary['target_only_header_count']}")
    print(f"missing_dependencies: {summary['missing_dependency_count']}")
    print("missing_dependency_classifications:")
    for classification, count in summary["missing_dependency_classification_counts"].items():
        print(f"  {classification}: {count}")
    print(f"batch_candidates: {summary['batch_candidate_count']}")
    print(f"mapped_headers: {summary['mapped_header_count']}")
    print(f"unmapped_tests: {summary['unmapped_test_count']}")
    print("status_counts:")
    for status, count in summary["status_counts"].items():
        print(f"  {status}: {count}")
    print(f"report: {report_path}")
    return 0


def cmd_migration_context(args) -> int:
    """Write the Node 11 bounded AI migration context pack for one header."""
    settings_path = Path(args.settings) if args.settings else DEFAULT_SETTINGS
    config = Config.load(settings_path, PROJECT_ROOT)
    output = args.output or default_context_pack_filename(args.entry_header)
    cccl_repo = _cli_cccl_repo(config, args)
    _inventory = scan_header_inventory(cccl_repo, include_root_rel=config.source_repo_prefix, symbol_dependency_rules=config.symbol_dependency_rules)
    pack = build_migration_context_pack_from_scans(
        entry_header=args.entry_header,
        cccl_repo=cccl_repo,
        target_repo=config.target_repo,
        examples_root=PROJECT_ROOT / "examples",
        ledger_path=DEFAULT_LEDGER_PATH,
        target_repo_prefix=config.target_repo_prefix,
        segment_substitutions=config.segment_substitutions,
        symbol_dependency_rules=config.symbol_dependency_rules,
        include_root_rel=config.source_repo_prefix,
        test_root_rel=config.cccl_test_prefix,
        state_status_map=_state_status_map(config, _inventory.header_root),
    )
    report_path = write_migration_context_pack(pack, config.output_dir, filename=output)
    print("== AI migration context pack ==")
    print(f"entry_header: {pack['entry_header']}")
    print(f"include: {pack['include']}")
    print(f"dependency_closure_size: {pack['dependency_closure']['closure_size']}")
    print(f"mapped_upstream_tests: {len(pack['mapped_upstream_tests'])}")
    print(f"nearby_accl_sibling_headers: {len(pack['nearby_accl_sibling_headers'])}")
    print(f"relevant_validated_examples: {len(pack['relevant_validated_examples'])}")
    print(f"target_counterpart_exists: {pack['existing_accl_counterpart']['exists']}")
    print(f"report: {report_path}")
    return 0


def cmd_folder_plan(args) -> int:
    """Analyze a source folder and produce a reviewable AI/heuristic migration plan."""
    settings_path = Path(args.settings) if args.settings else DEFAULT_SETTINGS
    if args.mock and args.real_ai:
        print("error: --mock and --real-ai are mutually exclusive", file=sys.stderr)
        return 2
    overrides = {"model": {"provider": "mock"}} if args.mock else None
    config = Config.load(settings_path, PROJECT_ROOT, overrides=overrides)
    cccl_repo = _cli_cccl_repo(config, args)

    inventory = scan_header_inventory(cccl_repo, include_root_rel=config.source_repo_prefix, symbol_dependency_rules=config.symbol_dependency_rules)
    test_index = scan_test_index(cccl_repo, include_root_rel=config.source_repo_prefix, test_root_rel=config.cccl_test_prefix)
    dep_graph = scan_dependency_graph(cccl_repo, include_root_rel=config.source_repo_prefix, symbol_dependency_rules=config.symbol_dependency_rules)
    status_report = _build_status_report_with_state(config, inventory, test_index, dep_graph)
    options = FolderPlanOptions(
        first_batch_size=args.first_batch_size,
        followup_batch_size=args.followup_batch_size,
        max_ai_candidates=args.max_ai_candidates,
    )
    try:
        plan = build_folder_plan_payload(
            config=config,
            source_dir=args.source_dir,
            inventory=inventory,
            test_index=test_index,
            dep_graph=dep_graph,
            status_report=status_report,
            options=options,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.real_ai:
        model_client = build_model_client(config)
        try:
            plan = refine_folder_plan_with_model(
                plan=plan,
                model_client=model_client,
                options=options,
                show_model_io=getattr(args, "show_model_io", False),
            )
        except Exception as exc:
            plan["model_recommendation_error"] = f"{type(exc).__name__}: {exc}"
            if not args.quiet:
                print(f"[folder-plan] 模型推荐失败，已保留确定性启发式计划：{plan['model_recommendation_error']}")
    elif args.mock:
        plan["model_recommendation"] = {
            "summary": "mock 模式未调用真实模型；使用确定性启发式推荐。",
            "first_batch": [item["source_header"] for item in plan["recommended_first_batch"]],
            "followup_batches": plan["followup_batches"],
            "risk_notes": [],
        }

    json_path, md_path = write_folder_plan(
        plan,
        config.output_dir,
        json_name=args.output_json,
        md_name=args.output_md,
    )
    summary = plan["summary"]
    print("== Folder migration planning ==")
    print(f"source_dir: {args.source_dir}")
    print(f"scope_relpath: {plan['scope_relpath'] or '.'}")
    print(f"mode: {'real_ai' if args.real_ai else ('mock/heuristic' if args.mock else 'heuristic')}")
    print(f"headers: {summary['header_count']}")
    print(f"eligible_candidates: {summary['eligible_candidate_count']}")
    print(f"blocked_or_deferred: {summary['blocked_or_deferred_count']}")
    print(f"independent_leaf_candidates: {summary.get('independent_leaf_candidate_count', 0)}")
    print(f"external_dependency_decisions: {summary.get('external_dependency_decision_count', 0)}")
    print("recommended_first_batch:")
    for item in plan["recommended_first_batch"]:
        print(f"  - {item['source_header']} ({item['complexity_label']}, score={item['complexity_score']})")
    print(f"json: {json_path}")
    print(f"markdown: {md_path}")
    print("next: review the markdown/json, then run folder-migrate with --approve")
    return 0


def _load_folder_plan(path: str | Path) -> dict:
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError(f"not a folder migration plan v1: {p}")
    return data


def _headers_from_folder_plan(plan: dict, batch: str) -> list[str]:
    def first_headers() -> list[str]:
        return [item["source_header"] for item in plan.get("recommended_first_batch") or []]

    def followup(name: str) -> list[str]:
        for item in plan.get("followup_batches") or []:
            if item.get("name") == name:
                return list(item.get("headers") or [])
        return []

    if batch == "first":
        return first_headers()
    if batch == "all":
        out = first_headers()
        for item in plan.get("followup_batches") or []:
            for header in item.get("headers") or []:
                if header not in out:
                    out.append(header)
        return out
    if batch.startswith("followup-"):
        return followup(batch)
    explicit = [item.strip() for item in batch.split(",") if item.strip()]
    known = {item["source_header"] for item in plan.get("headers") or []}
    return [header for header in explicit if header in known]


def _folder_external_dependency_issues(plan: dict, headers: list[str]) -> list[dict]:
    by_header = {
        item.get("source_header"): item
        for item in plan.get("headers") or []
        if isinstance(item, dict)
    }
    issues: list[dict] = []
    for header in headers:
        item = by_header.get(header) or {}
        if not item.get("external_dependency_approval_required"):
            continue
        issues.append({
            "source_header": header,
            "missing": [
                dep.get("dependency")
                for dep in item.get("external_missing_dependencies") or []
                if isinstance(dep, dict) and dep.get("dependency")
            ],
            "unverified": [
                dep.get("dependency")
                for dep in item.get("external_unverified_dependencies") or []
                if isinstance(dep, dict) and dep.get("dependency")
            ],
            "broken": [
                dep.get("dependency")
                for dep in item.get("external_broken_dependencies") or []
                if isinstance(dep, dict) and dep.get("dependency")
            ],
        })
    return issues


def _safe_report_name(header: str) -> str:
    return "dependency_convert_" + re.sub(r"[^0-9A-Za-z_.-]+", "__", header).strip("_") + ".json"


def _folder_dependency_args(args, header: str, *, cccl_repo: str) -> argparse.Namespace:
    return argparse.Namespace(
        settings=args.settings,
        entry_header=header,
        cccl_repo=cccl_repo,
        plan_only=args.plan_only,
        mock=args.mock,
        real_ai=args.real_ai,
        no_write_target=args.no_write_target,
        output=_safe_report_name(header),
        quiet=args.quiet,
        show_model_io=args.show_model_io,
        with_tests=args.with_tests,
        host_only=args.host_only,
        kernel_only=args.kernel_only,
        kernel_mode=args.kernel_mode,
        prepare_tests_only=args.prepare_tests_only,
        overwrite_tests=args.overwrite_tests,
        kernel_fast=args.kernel_fast,
        kernel_timeout=args.kernel_timeout,
        kernel_print_samples=args.kernel_print_samples,
        test_dry_run=args.test_dry_run,
        test_feedback_to_model=args.test_feedback_to_model,
        test_feedback_skill=args.test_feedback_skill,
        max_fix_rounds=args.max_fix_rounds,
        continue_on_test_failure=args.continue_on_test_failure,
        defer_dependents_on_failure=args.defer_dependents_on_failure,
        verify_includes=args.verify_includes,
        verify_includes_strict=args.verify_includes_strict,
    )


def cmd_folder_migrate(args) -> int:
    """Execute an approved batch from a folder migration plan."""
    if args.mock and args.real_ai:
        print("error: --mock and --real-ai are mutually exclusive", file=sys.stderr)
        return 2
    if not args.plan_only and not (args.mock or args.real_ai):
        print("error: choose --plan-only, --mock, or --real-ai explicitly", file=sys.stderr)
        return 2
    settings_path = Path(args.settings) if args.settings else DEFAULT_SETTINGS
    config = Config.load(settings_path, PROJECT_ROOT)
    cccl_repo = _cli_cccl_repo(config, args)
    try:
        plan = _load_folder_plan(args.plan)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: cannot load folder plan: {exc}", file=sys.stderr)
        return 2
    if not (args.approve or plan.get("approved")):
        print("error: plan is not approved. Review it, then pass --approve or set approved=true in the JSON.", file=sys.stderr)
        return 2

    headers = _headers_from_folder_plan(plan, args.batch)
    if args.limit:
        headers = headers[:args.limit]
    if not headers:
        print(f"error: no headers selected for batch {args.batch!r}", file=sys.stderr)
        return 2
    external_issues = _folder_external_dependency_issues(plan, headers)
    if external_issues and not (args.plan_only or args.allow_external_dependencies):
        print(
            "error: selected batch requires external dependency approval. "
            f"Review {args.plan} and pass --allow-external-dependencies to expand beyond the source scope.",
            file=sys.stderr,
        )
        for issue in external_issues:
            details = []
            if issue["missing"]:
                details.append("missing=" + ",".join(issue["missing"]))
            if issue["unverified"]:
                details.append("unverified=" + ",".join(issue["unverified"]))
            if issue["broken"]:
                details.append("broken=" + ",".join(issue["broken"]))
            print(f"  - {issue['source_header']}: {'; '.join(details)}", file=sys.stderr)
        return 2

    print("== Folder migration execution ==")
    print(f"plan: {args.plan}")
    print(f"batch: {args.batch}")
    print(f"cccl_repo: {cccl_repo}")
    print(f"headers: {len(headers)}")
    if external_issues:
        print(f"external_dependency_issues_approved: {len(external_issues)}")
    failed: list[str] = []
    for idx, header in enumerate(headers, start=1):
        print(f"\n---- [{idx}/{len(headers)}] {header} ----")
        dep_args = _folder_dependency_args(args, header, cccl_repo=cccl_repo)
        code = cmd_dependency_convert(dep_args)
        if code != 0:
            failed.append(header)
            if not args.continue_on_error:
                break

    if failed:
        print(f"\nfailed_headers: {', '.join(failed)}")
        return 2
    print("\nfolder migration batch complete")
    return 0


def cmd_dependency_convert(args) -> int:
    """Run the Node 12 dependency-aware header migration orchestration for one entry."""
    settings_path = Path(args.settings) if args.settings else DEFAULT_SETTINGS
    if args.mock and args.real_ai:
        print("error: --mock and --real-ai are mutually exclusive", file=sys.stderr)
        return 2
    if not args.plan_only and not (args.mock or args.real_ai):
        print("error: choose --plan-only, --mock, or --real-ai explicitly", file=sys.stderr)
        return 2

    overrides = {"model": {"provider": "mock"}} if args.mock or args.plan_only else None
    config = Config.load(settings_path, PROJECT_ROOT, overrides=overrides)
    cccl_repo = _cli_cccl_repo(config, args)

    inventory = scan_header_inventory(cccl_repo, include_root_rel=config.source_repo_prefix, symbol_dependency_rules=config.symbol_dependency_rules)
    test_index = scan_test_index(cccl_repo, include_root_rel=config.source_repo_prefix, test_root_rel=config.cccl_test_prefix)
    dep_graph = scan_dependency_graph(cccl_repo, include_root_rel=config.source_repo_prefix, symbol_dependency_rules=config.symbol_dependency_rules)
    status_report = _build_status_report_with_state(config, inventory, test_index, dep_graph)

    model_client = MockModelClient(responses=[]) if args.plan_only else (
        MockModelClient() if args.mock else build_model_client(config)
    )
    pipeline = Pipeline(
        config,
        model_client,
        verifier=None,
        verbose=not args.quiet,
        show_model_io=getattr(args, "show_model_io", False),
        toolbox=None if args.plan_only else _maybe_build_toolbox(config),
    )

    write_to_repo = not args.no_write_target
    on_rewritten = None
    run_tests = getattr(args, "with_tests", False) and not args.plan_only
    if run_tests:
        run_host, run_kernel = _resolve_test_selection(args)

        def on_rewritten(run_result):
            """紧跟每次 leaf-first 改写：迁移并跑该算子的 host/kernel 测试。

            返回 (is_failure, test_result)。环境类失败（无 cannsim/缺驱动等）与
            prepare/dry-run/skip 一律不计为失败，避免在开发机上误停整条闭包。
            """
            # _run_convert_test_loop 经 args.input 推导 CCCL 测试与目标头。
            args.input = run_result.input_path
            test_result = _run_convert_test_loop(
                args, config, model_client, run_result, write_to_repo
            )
            passed = _tests_all_passed(
                test_result, run_host, run_kernel, test_dry_run=args.test_dry_run
            )
            inconclusive = (
                args.prepare_tests_only
                or bool(test_result.get("skipped"))
                or _is_env_blocked(test_result)
            )
            is_failure = (not passed) and (not inconclusive)
            verdict = "FAIL" if is_failure else ("PASS" if passed else "INCONCLUSIVE")
            if not args.quiet:
                print(f"[test] {run_result.target_relpath}: {verdict}")
            # 通过则回写 migration_state：本条闭包内此头不会再遇到，价值在「下次重跑闭包时跳过」。
            _record_migration_state(
                config, input_path=run_result.input_path,
                target_relpath=run_result.target_relpath, test_result=test_result,
                run_host=run_host, run_kernel=run_kernel, args=args,
            )
            return is_failure, test_result

    result = pipeline.convert_dependency_closure(
        entry_header=args.entry_header,
        inventory=inventory,
        test_index=test_index,
        dep_graph=dep_graph,
        status_report=status_report,
        write_to_repo=write_to_repo,
        plan_only=args.plan_only,
        on_rewritten=on_rewritten,
        stop_on_test_failure=not getattr(args, "continue_on_test_failure", False),
        defer_dependents_on_failure=getattr(args, "defer_dependents_on_failure", False),
        verify_includes=getattr(args, "verify_includes", False),
        verify_includes_strict=getattr(args, "verify_includes_strict", False),
    )
    report_path = write_dependency_convert_report(config, result, args.output)

    print("== Node 12 dependency-aware header migration ==")
    print(f"entry_header: {result.entry_header}")
    print(f"mode: {_mode_label(plan_only=args.plan_only, mock=args.mock, real_ai=args.real_ai)}")
    print(f"model: {_model_label(config, plan_only=args.plan_only)}")
    print(f"ordered_headers: {len(result.ordered_headers)}")
    print(f"skipped_headers: {len(result.skipped_headers)}")
    print(f"rewritten_headers: {len(result.rewritten_headers)}")
    if run_tests:
        tested = sum(1 for it in result.items if it.action == "rewritten")
        print(f"tested_headers: {tested}")
        print(f"failed_test_headers: {len(result.failed_test_headers)}"
              + (f" -> {', '.join(result.failed_test_headers)}" if result.failed_test_headers else ""))
    print(f"complete: {result.complete}")
    if result.error:
        print(f"error: {result.error}")
    print(f"report: {report_path}")
    return 2 if (result.error or result.failed_test_headers) else 0


def _split_csv(value) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _build_package_plan(config: Config, cccl_repo: str, manual_marks: set[str]) -> dict:
    """Scan the whole CCCL package and build the dependency-wave plan (no model)."""
    inventory = scan_header_inventory(
        cccl_repo, include_root_rel=config.source_repo_prefix, symbol_dependency_rules=config.symbol_dependency_rules
    )
    test_index = scan_test_index(
        cccl_repo, include_root_rel=config.source_repo_prefix, test_root_rel=config.cccl_test_prefix
    )
    dep_graph = scan_dependency_graph(
        cccl_repo, include_root_rel=config.source_repo_prefix, symbol_dependency_rules=config.symbol_dependency_rules
    )
    status_report = _build_status_report_with_state(config, inventory, test_index, dep_graph)
    return build_package_plan_payload(
        config=config,
        inventory=inventory,
        dep_graph=dep_graph,
        test_index=test_index,
        status_report=status_report,
        manual_marks=manual_marks,
    )


def cmd_package_plan(args) -> int:
    """Build/refresh the whole-package dependency-wave migration plan (no model)."""
    settings_path = Path(args.settings) if args.settings else DEFAULT_SETTINGS
    config = Config.load(settings_path, PROJECT_ROOT)
    cccl_repo = _cli_cccl_repo(config, args)

    # 持久化的人工标记：先读既有计划，再叠加本次 --mark / --unmark。
    marks = read_manual_marks(config.output_dir / args.output_json)
    for header in _split_csv(args.mark):
        marks.add(header)
    for header in _split_csv(args.unmark):
        marks.discard(header)

    plan = _build_package_plan(config, cccl_repo, marks)
    json_path, md_path = write_package_plan(
        plan, config.output_dir, json_name=args.output_json, md_name=args.output_md
    )
    summary = plan["summary"]
    print("== Package migration planning (dependency waves) ==")
    print(f"cccl_repo: {plan['cccl_repo']}")
    print(f"header_root: {plan['header_root']}")
    print(f"total_headers: {summary['total_headers']}")
    print(f"completed: {summary['completed']}")
    print(f"pending: {summary['pending']}")
    print(f"deferred: {summary['deferred']}")
    print(f"blocked: {summary['blocked']}")
    print(f"batches: {summary['batch_count']} (cycles: {summary['cycle_count']})")
    for batch in plan["batches"][:10]:
        flag = " [cycle]" if batch["contains_cycle"] else ""
        print(f"  {batch['name']}: {batch['header_count']} headers{flag}")
    if summary["batch_count"] > 10:
        print(f"  ... +{summary['batch_count'] - 10} more batches")
    print(f"json: {json_path}")
    print(f"markdown: {md_path}")
    print("next: review, then run package-migrate --batch next --approve --real-ai --with-tests")
    return 0


def cmd_package_migrate(args) -> int:
    """Execute an approved batch from a package plan, then refresh the ledger."""
    if args.mock and args.real_ai:
        print("error: --mock and --real-ai are mutually exclusive", file=sys.stderr)
        return 2
    if not args.plan_only and not (args.mock or args.real_ai):
        print("error: choose --plan-only, --mock, or --real-ai explicitly", file=sys.stderr)
        return 2
    settings_path = Path(args.settings) if args.settings else DEFAULT_SETTINGS
    config = Config.load(settings_path, PROJECT_ROOT)
    cccl_repo = _cli_cccl_repo(config, args)
    try:
        plan = load_package_plan(args.plan)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: cannot load package plan: {exc}", file=sys.stderr)
        return 2
    if not (args.approve or plan.get("approved")):
        print(
            "error: plan is not approved. Review it, then pass --approve or set approved=true in the JSON.",
            file=sys.stderr,
        )
        return 2

    completed = plan_completed_set(plan)
    headers = headers_for_batch(plan, args.batch, completed)
    if args.limit:
        headers = headers[: args.limit]
    if not headers:
        if args.batch in ("next", "all"):
            print("package migration: nothing left to migrate for this selection.")
            return 0
        print(f"error: no headers selected for batch {args.batch!r}", file=sys.stderr)
        return 2

    print("== Package migration execution ==")
    print(f"plan: {args.plan}")
    print(f"batch: {args.batch}")
    print(f"cccl_repo: {cccl_repo}")
    print(f"headers: {len(headers)}")
    failed: list[str] = []
    for idx, header in enumerate(headers, start=1):
        print(f"\n---- [{idx}/{len(headers)}] {header} ----")
        dep_args = _folder_dependency_args(args, header, cccl_repo=cccl_repo)
        code = cmd_dependency_convert(dep_args)
        if code != 0:
            failed.append(header)
            if not args.continue_on_error:
                break

    # 迁移后刷新台账：把新通过的头自动标记、重算波次（plan_only 不改状态，跳过刷新）。
    if not args.plan_only:
        plan_path = Path(args.plan)
        refreshed = _build_package_plan(config, cccl_repo, read_manual_marks(plan_path))
        refreshed["approved"] = bool(plan.get("approved") or args.approve)
        write_package_plan(
            refreshed, plan_path.parent, json_name=plan_path.name, md_name=plan_path.stem + ".md"
        )
        print(
            f"\nplan refreshed: completed={refreshed['summary']['completed']}, "
            f"pending={refreshed['summary']['pending']}"
        )

    if failed:
        print(f"\nfailed_headers: {', '.join(failed)}")
        return 2
    print("\npackage migration batch complete")
    return 0
