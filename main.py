"""ASC_agent 命令行入口。

子命令：
    convert  只做「生成 -> 写入目标仓库 -> 可选跑测试」，跳过 git 提交（推荐的全流程入口）
    run      迁移单个 CCCL 文件，含 git 提交检查与多轮修复（真实或 --mock）
    batch    按清单批量迁移并产出汇总报告（工具链 + 测试能力的核心）
    test     为指定算子生成并执行 host/kernel 测试
    selftest 用内置示例做一次离线冒烟（mock，无需仓库/网络）

用法：
    python main.py convert --input <CCCL 文件路径> --with-tests
    python main.py run     --input <CCCL 文件路径> [--mock] [--dry-run]
    python main.py batch   --manifest <manifest.yaml> [--mock] [--quiet]
    python main.py test    --input <CCCL 文件路径> [--host-only | --kernel-only]
    python main.py selftest
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from core.agent_tools import build_toolbox, distill_error_lines
from core.config import Config
from core.dep_graph import scan_dependency_graph, write_dependency_graph_report
from core.example_promote import discover_promotable, promote_operator
from core.fix_once import run_single_fix_from_test_feedback, run_test_artifact_fix
from core.inventory import scan_header_inventory, write_inventory_report
from core.migration_status import scan_migration_status, write_migration_status_report
from core.model_client import MockModelClient, build_model_client
from core.operator_test import OperatorTestRunner
from core.path_mapper import expected_guard_from_relpath, map_cccl_test_path, map_target_relpath
from core.pipeline import FakeVerifier, Pipeline, RunResult
from core.repo_verify import RepoVerifier
from core.sample_revalidation import build_sample_revalidation_report, write_sample_revalidation_report
from core.test_index import scan_test_index, write_test_index_report
from core.test_migrator import migrate_operator_tests
from core.utils import save_text

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_SETTINGS = PROJECT_ROOT / "config" / "settings.yaml"


# --------------------------------------------------------------------------- #
# 装配
# --------------------------------------------------------------------------- #
def make_components(mock: bool, dry_run: bool, verbose: bool,
                    settings_path: Path, rounds_to_pass: int = 0, fake_verifier: bool = False):
    """根据开关返回 (config, model_client, verifier)。"""
    overrides = {"model": {"provider": "mock"}} if mock else None
    config = Config.load(settings_path, PROJECT_ROOT, overrides=overrides)

    if mock:
        model_client = MockModelClient()
        verifier = FakeVerifier(config, rounds_to_pass=rounds_to_pass, verbose=verbose)
    elif fake_verifier:
        model_client = build_model_client(config)
        verifier = FakeVerifier(config, rounds_to_pass=rounds_to_pass, verbose=verbose)
    else:
        model_client = build_model_client(config)
        verifier = RepoVerifier(config, dry_run=dry_run, verbose=verbose)
    return config, model_client, verifier


# --------------------------------------------------------------------------- #
# 报告
# --------------------------------------------------------------------------- #
def write_batch_report(config: Config, results: list[RunResult]) -> Path:
    total = len(results)
    pushed = sum(1 for r in results if r.pushed)
    commit_ok = sum(1 for r in results if r.commit_passed)
    converted = sum(1 for r in results if r.converted)

    report = {
        "summary": {
            "total": total,
            "converted": converted,
            "commit_passed": commit_ok,
            "pushed": pushed,
            "push_rate": round(pushed / total, 3) if total else 0.0,
        },
        "results": [r.to_dict() for r in results],
    }
    report_path = config.output_dir / "batch_report.json"
    save_text(report_path, json.dumps(report, ensure_ascii=False, indent=2))
    return report_path


def print_batch_table(results: list[RunResult]) -> None:
    print("\n================ 批量结果汇总 ================")
    header = f"{'file':<24}{'conv':>5}{'base':>6}{'commit':>8}{'rounds':>8}{'push':>6}{'test':>6}"
    print(header)
    print("-" * len(header))
    for r in results:
        name = Path(r.input_path).name
        test_status = "-"
        if r.test_result:
            host_ok = r.test_result.get("host_passed", True)
            kernel_ok = r.test_result.get("kernel_passed", True)
            if r.test_result.get("error"):
                test_status = "ERR"
            else:
                test_status = "Y" if host_ok and kernel_ok else "N"
        print(
            f"{name:<24}"
            f"{'Y' if r.converted else 'N':>5}"
            f"{'Y' if r.baseline_formed else 'N':>6}"
            f"{'Y' if r.commit_passed else 'N':>8}"
            f"{r.rounds_used:>8}"
            f"{'Y' if r.pushed else 'N':>6}"
            f"{test_status:>6}"
        )
        if r.error:
            print(f"    └─ error: {r.error}")
        if r.test_result and r.test_result.get("error"):
            print(f"    └─ test_error: {r.test_result['error']}")
    total = len(results)
    pushed = sum(1 for r in results if r.pushed)
    print("-" * len(header))
    print(f"总计 {total} 个文件，push 成功 {pushed} 个"
          f"（{(pushed / total * 100):.1f}%）" if total else "无文件")


def _resolve_test_selection(args) -> tuple[bool, bool]:
    if getattr(args, "host_only", False):
        return True, False
    if getattr(args, "kernel_only", False):
        return False, True
    return True, True


def _host_test_file_for(config: Config, target_relpath: str) -> Path:
    """ACCL host 测试文件路径（与 OperatorTestRunner 的目录约定一致）。"""
    algo = OperatorTestRunner.algo_name_from_target_relpath(target_relpath)
    return (
        Path(config.target_repo)
        / "libascendcxx" / "test" / "libascendcxx" / "ascend" / "host"
        / f"{algo}_tests.cpp"
    )


def _maybe_migrate_tests(
    args,
    config: Config,
    model_client,
    *,
    input_path,
    target_relpath: str,
    verbose: bool = True,
) -> dict | None:
    """用模型把 CCCL 侧测试迁移为 ACCL host 测试 + kernel_spec。

    不可用时返回 None（调用方回退到内置模板）：mock / test-dry-run / 无 model /
    找不到 CCCL 测试 / 未找到已迁移的 ACCL 头 / 迁移异常。
    """
    if getattr(args, "mock", False) or getattr(args, "test_dry_run", False):
        return None
    if model_client is None or not input_path:
        return None
    try:
        cccl_test_path = Path(
            map_cccl_test_path(
                Path(input_path),
                source_repo_prefix=config.source_repo_prefix,
                cccl_test_prefix=config.cccl_test_prefix,
                suffix=config.cccl_test_suffix,
            )
        )
    except ValueError:
        return None
    if not cccl_test_path.exists():
        if verbose:
            print(f"[test-migrate] 未找到 CCCL 侧测试 {cccl_test_path}，回退内置模板。")
        return None
    accl_header = Path(config.target_repo) / target_relpath
    if not accl_header.exists():
        if verbose:
            print(f"[test-migrate] 未找到已迁移的 ACCL 头 {accl_header}，回退内置模板。")
        return None

    algo_name = OperatorTestRunner.algo_name_from_target_relpath(target_relpath)
    include_path = OperatorTestRunner.include_path_from_target_relpath(target_relpath)
    try:
        artifacts = migrate_operator_tests(
            config,
            model_client,
            algo_name=algo_name,
            include_path=include_path,
            target_relpath=target_relpath,
            cccl_header_text=Path(input_path).read_text(encoding="utf-8"),
            accl_header_text=accl_header.read_text(encoding="utf-8"),
            cccl_test_text=cccl_test_path.read_text(encoding="utf-8"),
            verbose=verbose,
            show_model_io=getattr(args, "show_model_io", False),
            toolbox=_maybe_build_toolbox(config),  # 生成期取证/自检（默认关闭→None）
            max_tool_rounds=config.model_max_tool_rounds,
        )
    except Exception as exc:  # 迁移失败不应中断流程，回退模板
        if verbose:
            print(f"[test-migrate] 迁移失败（{type(exc).__name__}: {exc}），回退内置模板。")
        return None
    return {"host_test_code": artifacts.host_test_code, "kernel_spec": artifacts.kernel_spec}


def _run_operator_tests(
    args,
    config: Config,
    target_relpath: str,
    *,
    require_ready_commit: bool = False,
    commit_passed: bool = True,
    skip_in_mock: bool = True,
    test_artifacts: dict | None = None,
) -> dict:
    if require_ready_commit and not commit_passed:
        return {"skipped": True, "reason": "commit_not_passed"}
    if args.mock and skip_in_mock:
        return {"skipped": True, "reason": "mock_mode_no_real_model"}

    run_host, run_kernel = _resolve_test_selection(args)
    kernel_timeout = getattr(args, "kernel_timeout", 0) or None
    kernel_fast = True if getattr(args, "kernel_fast", False) else None
    runner = OperatorTestRunner(
        config,
        verbose=not args.quiet,
        dry_run=args.test_dry_run,
        kernel_timeout_sec=kernel_timeout,
        fast_kernel=kernel_fast,
        kernel_print_samples=getattr(args, "kernel_print_samples", None),
    )
    artifacts = test_artifacts or {}
    tr = runner.prepare_and_run(
        target_relpath=target_relpath,
        run_host=run_host,
        run_kernel=run_kernel,
        kernel_mode=args.kernel_mode,
        prepare_only=args.prepare_tests_only,
        overwrite=args.overwrite_tests,
        host_test_code=artifacts.get("host_test_code"),
        kernel_spec=artifacts.get("kernel_spec"),
    )
    return tr.to_dict()


def _tests_all_passed(test_result: dict, run_host: bool, run_kernel: bool, test_dry_run: bool = False) -> bool:
    if test_result.get("error"):
        return False
    if test_result.get("skipped"):
        return True
    if test_dry_run:
        return True
    # 被预检跳过的一侧（如无 cannsim 跳过 kernel）不计为失败。
    if (
        run_host
        and not test_result.get("host_passed", False)
        and test_result.get("host_failure_kind") != "skipped"
    ):
        return False
    if (
        run_kernel
        and not test_result.get("kernel_passed", False)
        and test_result.get("kernel_failure_kind") != "skipped"
    ):
        return False
    return True


def _is_env_blocked(test_result: dict) -> bool:
    """测试失败是否属于「环境问题」（改代码无用，不应回传模型修复）。"""
    return "env" in (
        test_result.get("host_failure_kind"),
        test_result.get("kernel_failure_kind"),
    )


def _resolve_target_relpath_for_test(args, config: Config) -> str:
    if args.target_relpath:
        return args.target_relpath
    if not args.input:
        raise ValueError("test 子命令需要 --input 或 --target-relpath 之一")
    return map_target_relpath(
        input_path=Path(args.input),
        source_repo_prefix=config.source_repo_prefix,
        target_repo_prefix=config.target_repo_prefix,
        segment_substitutions=config.segment_substitutions,
    )


def _safe_read_text(path: Path, max_chars: int = 12000) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8")
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[truncated]"


def _read_and_distill_log(path_str: str, *, max_chars: int = 8000) -> str:
    """读整份日志再蒸馏出 error/warning 行及上下文。

    比旧的「按 12k 字节硬截断」更可靠：cannsim/编译日志常有数万行，真正的报错往往在
    末尾或中段，硬截断会把它截没；蒸馏只保留有信号的行，既省 token 又不丢现场。
    """
    if not path_str:
        return ""
    p = Path(path_str)
    if not p.exists():
        return ""
    text = p.read_text(encoding="utf-8", errors="replace")
    return distill_error_lines(text, max_chars=max_chars).strip()


def _build_test_feedback_text(test_result: dict) -> str:
    lines: list[str] = []
    host_state = "PASSED" if test_result.get("host_passed") else "FAILED"
    kernel_state = "PASSED" if test_result.get("kernel_passed") else "FAILED"
    lines.append(f"host_result: {host_state}")
    lines.append(f"kernel_result: {kernel_state}")

    host_text = _read_and_distill_log(test_result.get("host_log_path"))
    if host_text:
        lines.append("\n[host_log（已蒸馏 error 行）]\n" + host_text)

    kernel_text = _read_and_distill_log(test_result.get("kernel_log_path"))
    if kernel_text:
        lines.append("\n[kernel_log（已蒸馏 error 行）]\n" + kernel_text)

    if test_result.get("error"):
        lines.append("\n[test_runner_error]\n" + str(test_result["error"]))
    return "\n".join(lines).strip()


def _read_commit_feedback_text(config: Config, rounds_used: int) -> str:
    out = config.output_dir
    candidates = [
        out / f"git_commit_round{rounds_used}.log",
        out / "git_commit.log",
    ]
    for p in candidates:
        text = _safe_read_text(p)
        if text.strip():
            return text
    return "commit hook result unavailable in outputs; focus on provided test feedback."


def _generate_model_fix_from_test_feedback(
    *,
    args,
    config: Config,
    model_client,
    target_relpath: str,
    expected_header_guard: str,
    test_result: dict,
    rounds_used: int = 0,
) -> dict:
    if args.mock:
        return {"skipped": True, "reason": "mock_mode_no_real_model"}
    if args.test_dry_run:
        return {"skipped": True, "reason": "test_dry_run_enabled"}

    commit_text = _read_commit_feedback_text(config, rounds_used)
    test_text = _build_test_feedback_text(test_result)
    if not test_text:
        return {"skipped": True, "reason": "empty_test_feedback"}

    fixed = run_single_fix_from_test_feedback(
        config=config,
        model_client=model_client,
        target_relpath=target_relpath,
        expected_header_guard=expected_header_guard,
        commit_log_text=commit_text,
        test_feedback_text=test_text,
        prompt_filename=args.test_feedback_skill,
        verbose=not args.quiet,
        show_model_io=getattr(args, "show_model_io", False),
    )
    return {
        "skipped": False,
        "fixed_target_path": str(fixed),
        "request_path": str(config.output_dir / "fix_request_test_feedback.md"),
        "result_json_path": str(config.output_dir / "fix_result_test_feedback.json"),
    }


# --------------------------------------------------------------------------- #
# 子命令
# --------------------------------------------------------------------------- #
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


def _maybe_build_toolbox(config: Config):
    """启用 model.tools_enabled（且非 mock）时构建模型工具箱；否则返回 None。

    迁移 / 测试迁移 / 测试反馈修复三条链路共用 core.agent_tools.build_toolbox（单一事实源）。
    """
    return build_toolbox(config)


def _format_attempt_history(rounds_log: list[dict]) -> str:
    """把历轮（根因 / 改了哪些件 / 是否通过）压成紧凑摘要，回喂模型形成跨轮记忆。

    没有它时每轮都是「无状态盲改」，模型可能反复提交同一个被证明无效的修复；有了它，
    模型能看到「上轮按 X 根因改了 header 仍失败」，从而换思路而不是原地打转。
    """
    if not rounds_log:
        return ""
    parts: list[str] = []
    for r in rounds_log:
        applied = ", ".join(r.get("applied") or []) or "无改动"
        outcome = "通过" if r.get("passed") else "仍失败"
        rc = r.get("root_cause", "") or "未判定"
        line = f"- 第{r.get('round')}轮：根因={rc}；改动=[{applied}]；结果={outcome}"
        if r.get("test_error"):
            line += f"；runner错误={str(r['test_error'])[:120]}"
        parts.append(line)
    return "\n".join(parts)


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
    model_client = None
    if args.test_feedback_to_model:
        model_client = MockModelClient() if args.mock else build_model_client(config)

    # 有真实模型且给了 --input 时，迁移该算子的测试（host + kernel_spec）。
    artifacts = _maybe_migrate_tests(
        args, config, model_client,
        input_path=getattr(args, "input", None), target_relpath=target_relpath, verbose=not args.quiet,
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
            model_client=model_client,
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
    report = scan_header_inventory(args.cccl_repo)
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
    report = scan_test_index(args.cccl_repo)
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


def cmd_dep_graph(args) -> int:
    """Scan CCCL headers and write a deterministic include dependency graph report."""
    settings_path = Path(args.settings) if args.settings else DEFAULT_SETTINGS
    config = Config.load(settings_path, PROJECT_ROOT)
    report = scan_dependency_graph(args.cccl_repo)
    report_path = write_dependency_graph_report(report, config.output_dir, filename=args.output)
    summary = report.summary()
    print("== CCCL libcudacxx include dependency graph ==")
    print(f"cccl_repo: {report.cccl_repo}")
    print(f"header_root: {report.header_root}")
    print(f"headers: {summary['header_count']}")
    print(f"edges: {summary['edge_count']}")
    print(f"cycles: {summary['cycle_count']}")
    print(f"unknown_cuda_std_includes: {summary['unknown_cuda_std_include_count']}")
    print(f"report: {report_path}")
    return 0


def cmd_revalidate_samples(args) -> int:
    """Write the Node 6 real-upstream sample revalidation report."""
    settings_path = Path(args.settings) if args.settings else DEFAULT_SETTINGS
    config = Config.load(settings_path, PROJECT_ROOT)
    report = build_sample_revalidation_report(
        args.cccl_repo,
        target_repo=config.target_repo,
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
    report = scan_migration_status(
        args.cccl_repo,
        target_repo=config.target_repo,
        ledger_path=PROJECT_ROOT / "docs" / "migration_ledger.md",
        target_repo_prefix=config.target_repo_prefix,
        segment_substitutions=config.segment_substitutions,
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
    print(f"mapped_headers: {summary['mapped_header_count']}")
    print(f"unmapped_tests: {summary['unmapped_test_count']}")
    print("status_counts:")
    for status, count in summary["status_counts"].items():
        print(f"  {status}: {count}")
    print(f"report: {report_path}")
    return 0


# --------------------------------------------------------------------------- #
# 解析
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CCCL -> ACCL v3 迁移工具链")
    parser.add_argument("--settings", help="settings.yaml 路径（默认 config/settings.yaml）")
    sub = parser.add_subparsers(dest="command", required=True)

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
    p_test.add_argument("--target-relpath", help="直接指定目标相对路径（如 libascendcxx/include/ascend/std/__algorithm/max.h）")
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
        help="真实 CCCL 仓库根目录；默认取 CCCL_REPO，再退到 /home/zhenyu/projects/cccl",
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
        help="真实 CCCL 仓库根目录；默认取 CCCL_REPO，再退到 /home/zhenyu/projects/cccl",
    )
    p_test_index.add_argument(
        "--output",
        default="cccl_test_index.json",
        help="写入 outputs/ 下的报告文件名",
    )
    p_test_index.set_defaults(func=cmd_test_index)

    p_dep_graph = sub.add_parser(
        "dep-graph",
        help="只读扫描真实 CCCL libcudacxx headers，并写入 include dependency graph 报告",
    )
    p_dep_graph.add_argument(
        "--cccl-repo",
        help="真实 CCCL 仓库根目录；默认取 CCCL_REPO，再退到 /home/zhenyu/projects/cccl",
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
        help="真实 CCCL 仓库根目录；默认取 CCCL_REPO，再退到 /home/zhenyu/projects/cccl",
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
        help="真实 CCCL 仓库根目录；默认取 CCCL_REPO，再退到 /home/zhenyu/projects/cccl",
    )
    p_status.add_argument(
        "--output",
        default="migration_status.json",
        help="写入 outputs/ 下的报告文件名",
    )
    p_status.set_defaults(func=cmd_migration_status)

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


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
