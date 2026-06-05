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

from core.agent_tools import AgentToolbox
from core.config import Config
from core.fix_once import run_single_fix_from_test_feedback, run_test_artifact_fix
from core.model_client import MockModelClient, build_model_client
from core.operator_test import OperatorTestRunner
from core.path_mapper import expected_guard_from_relpath, map_cccl_test_path, map_target_relpath
from core.pipeline import FakeVerifier, Pipeline, RunResult
from core.repo_verify import RepoVerifier
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


def _build_test_feedback_text(test_result: dict) -> str:
    lines: list[str] = []
    host_state = "PASSED" if test_result.get("host_passed") else "FAILED"
    kernel_state = "PASSED" if test_result.get("kernel_passed") else "FAILED"
    lines.append(f"host_result: {host_state}")
    lines.append(f"kernel_result: {kernel_state}")

    host_log = test_result.get("host_log_path")
    if host_log:
        host_text = _safe_read_text(Path(host_log))
        if host_text.strip():
            lines.append("\n[host_log]\n" + host_text)

    kernel_log = test_result.get("kernel_log_path")
    if kernel_log:
        kernel_text = _safe_read_text(Path(kernel_log))
        if kernel_text.strip():
            lines.append("\n[kernel_log]\n" + kernel_text)

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
                        show_model_io=getattr(args, "show_model_io", False))
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
    """启用 model.tools_enabled 时构建模型工具箱（取证 + host 自检）；否则返回 None。"""
    if not config.model_tools_enabled:
        return None
    include_dir = Path(config.target_repo) / "libascendcxx" / "include"
    return AgentToolbox(
        target_repo=Path(config.target_repo),
        output_dir=config.output_dir,
        host_include_dirs=[include_dir],
    )


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
                        show_model_io=getattr(args, "show_model_io", False))
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
                            show_model_io=getattr(args, "show_model_io", False))
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

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
