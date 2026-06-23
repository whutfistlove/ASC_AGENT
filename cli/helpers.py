"""CLI helper layer: assembly, reporting, test execution, migration-state and
model-feedback construction. Pure functions shared by the command implementations.
"""
from __future__ import annotations

import json
from pathlib import Path

from core.analysis.migration_status import (
    build_migration_status_report,
)
from core.analysis.path_mapper import map_cccl_test_path, map_target_relpath
from core.analysis.test_index import scan_test_index
from core.common.config import Config
from core.common.utils import save_text
from core.llm.agent_tools import build_toolbox, distill_error_lines
from core.llm.model_client import MockModelClient, build_model_client
from core.migration.fix_once import run_single_fix_from_test_feedback
from core.migration.pipeline import FakeVerifier, RunResult
from core.repo.repo_verify import RepoVerifier
from core.testing.operator_test import OperatorTestRunner
from core.testing.test_migrator import (
    migrate_operator_tests,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SETTINGS = PROJECT_ROOT / "config" / "settings.yaml"
DEFAULT_LEDGER_PATH = PROJECT_ROOT / "docs" / "migration_ledger.md"


def _mode_label(*, plan_only: bool = False, mock: bool = False, real_ai: bool = False) -> str:
    if plan_only:
        return "plan_only (只规划；不调用模型；不写 ACCL)"
    if mock:
        return "mock (离线模拟模型；不调用真实 API)"
    if real_ai:
        return "real_ai (真实模型/API 调用)"
    return "unknown"


def _model_label(config: Config, *, plan_only: bool = False) -> str:
    if plan_only:
        return "none (plan_only)"
    if config.model_provider == "mock":
        return f"mock (无真实 API 调用；配置 model_name={config.model_name})"
    return f"{config.model_provider}/{config.model_name}"


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


def write_dependency_convert_report(config: Config, result, output: str) -> Path:
    name = Path(output)
    if name.is_absolute() or len(name.parts) != 1:
        raise ValueError("dependency convert report filename must be a file name under outputs/")
    report_path = config.output_dir / name
    save_text(report_path, json.dumps(result.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n")
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
        / "asc-stl" / "test" / "asc-stl" / "asc" / "host"
        / f"{algo}_tests.cpp"
    )


def _infer_real_cccl_root_and_entry_header(
    input_path: Path, marker: str = "libcudacxx/include/cuda/std/"
) -> tuple[Path, str] | None:
    """Infer CCCL root and namespace-relative header from a real libcudacxx path.

    `marker` 是 `source_repo_prefix` 末尾补 `/`：std 层为 `.../cuda/std/`，
    扩展层为 `.../cuda/`，使 entry_header 相对各自命名空间根求出。
    """
    marker = marker.rstrip("/") + "/"
    path_text = str(input_path.resolve()).replace("\\", "/")
    if marker not in path_text:
        return None
    root_text, entry_header = path_text.split(marker, 1)
    if not entry_header:
        return None
    return Path(root_text.rstrip("/")), entry_header


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
    test_index = None
    entry_header = ""
    inferred = _infer_real_cccl_root_and_entry_header(
        Path(input_path), marker=config.source_repo_prefix
    )
    if inferred is not None:
        cccl_root, entry_header = inferred
        try:
            test_index = scan_test_index(
                cccl_root,
                include_root_rel=config.source_repo_prefix,
                test_root_rel=config.cccl_test_prefix,
            )
        except Exception as exc:
            if verbose:
                print(f"[test-migrate] real test-index 扫描失败（{type(exc).__name__}: {exc}），使用 legacy 测试路径。")
    legacy_test_text = ""
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
        cccl_test_path = None
    if cccl_test_path and cccl_test_path.exists():
        legacy_test_text = cccl_test_path.read_text(encoding="utf-8")
    elif test_index is None:
        if verbose:
            missing = cccl_test_path or "<unmapped>"
            print(f"[test-migrate] 未找到 CCCL 侧测试 {missing}，回退内置模板。")
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
            cccl_test_text=legacy_test_text,
            test_index=test_index,
            entry_header=entry_header,
            verbose=verbose,
            show_model_io=getattr(args, "show_model_io", False),
            toolbox=_maybe_build_toolbox(config),  # 生成期取证/自检（默认关闭→None）
            max_tool_rounds=config.model_max_tool_rounds,
        )
    except Exception as exc:  # 迁移失败不应中断流程，回退模板
        if verbose:
            print(f"[test-migrate] 迁移失败（{type(exc).__name__}: {exc}），回退内置模板。")
        return None
    return {
        "host_test_code": artifacts.host_test_code,
        "kernel_spec": artifacts.kernel_spec,
        "upstream_test_plan": (
            artifacts.upstream_test_plan.to_dict()
            if artifacts.upstream_test_plan is not None
            else None
        ),
    }


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
    result = tr.to_dict()
    if artifacts.get("upstream_test_plan") is not None:
        result["test_migration_plan"] = artifacts["upstream_test_plan"]
    return result


def _dimension_semantic_passed(test_result: dict, dimension: str) -> bool:
    """Return true only when a test dimension has real semantic coverage.

    Older result dictionaries only had host_passed/kernel_passed.  Newer ones
    explicitly distinguish semantic_passed from smoke_passed; when those fields
    exist, smoke is never accepted as a pass.
    """
    semantic_key = f"{dimension}_semantic_passed"
    smoke_key = f"{dimension}_smoke_passed"
    if semantic_key in test_result or smoke_key in test_result:
        return bool(test_result.get(semantic_key))
    return bool(test_result.get(f"{dimension}_passed"))


def _dimension_state(test_result: dict, dimension: str) -> str:
    if _dimension_semantic_passed(test_result, dimension):
        return "PASSED"
    if test_result.get(f"{dimension}_smoke_passed"):
        return "SMOKE"
    if test_result.get(f"{dimension}_failure_kind") == "skipped":
        return "SKIPPED"
    return "FAILED"


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
        and not _dimension_semantic_passed(test_result, "host")
        and test_result.get("host_failure_kind") != "skipped"
    ):
        return False
    if (
        run_kernel
        and not _dimension_semantic_passed(test_result, "kernel")
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


def _cli_cccl_repo(config: Config, args) -> str:
    """Resolve the CCCL repo for CLI commands from args, then config.

    Core scan helpers still have a low-level fallback for isolated library
    tests, but CLI commands should always honor the project config default.
    """
    raw = getattr(args, "cccl_repo", None) or config.cccl_repo
    path = Path(str(raw)).expanduser()
    if not path.is_absolute():
        path = config.project_root / path
    return str(path)


def _state_store_path(config: Config) -> Path:
    from core.analysis.migration_state import DEFAULT_STATE_FILENAME

    return config.output_dir / DEFAULT_STATE_FILENAME


def _state_status_map(config: Config, header_root: str) -> dict:
    """读取自动维护的迁移状态作为「已验证证据」（带源文件新鲜度过滤）。"""
    from core.analysis.migration_state import MigrationStateStore

    return MigrationStateStore.load(_state_store_path(config)).fresh_status_map(header_root)


def _build_status_report_with_state(config: Config, inventory, test_index, dep_graph):
    """统一构建迁移状态报告：手写 ledger + 自动验证状态（state store）双证据。"""
    return build_migration_status_report(
        inventory=inventory,
        test_index=test_index,
        dep_graph=dep_graph,
        target_repo=config.target_repo,
        ledger_path=DEFAULT_LEDGER_PATH,
        target_repo_prefix=config.target_repo_prefix,
        segment_substitutions=config.segment_substitutions,
        state_status_map=_state_status_map(config, inventory.header_root),
        policy=config.migration_policy,
    )


def _record_migration_state(config: Config, *, input_path, target_relpath, test_result,
                            run_host: bool, run_kernel: bool, args) -> None:
    """把一次确定的 host/kernel 测试结论回写进 migration_state（闭合 能测 → 能扩）。

    只在「真实跑了语义测试且按所测维度全部通过」时记录：dry-run / prepare-only / mock / skipped /
    runner 出错 一律跳过；某维度因无 cannsim 等被预检跳过不算失败（与 `_tests_all_passed`
    口径一致）。SMOKE 只代表脚手架能编译/启动，不能写入状态。这样：两侧都过→full_passed；仅 kernel 过→kernel_passed；仅 host 过（kernel 被
    跳过）→host_passed；host 过但 kernel code-fail→不记录（保持 generated，下次重迁重试 kernel）。
    """
    if not test_result:
        return
    if getattr(args, "test_dry_run", False) or getattr(args, "prepare_tests_only", False) or getattr(args, "mock", False):
        return
    if test_result.get("skipped") or test_result.get("error"):
        return
    if not _tests_all_passed(test_result, run_host, run_kernel, test_dry_run=False):
        return
    host_passed = _dimension_semantic_passed(test_result, "host") if run_host else False
    kernel_passed = _dimension_semantic_passed(test_result, "kernel") if run_kernel else False
    if not host_passed and not kernel_passed:
        return

    from core.analysis.migration_state import MigrationStateStore
    from core.analysis.path_mapper import source_header_relpath

    src = Path(input_path) if input_path else None
    source_header = source_header_relpath(src, config.source_repo_prefix) if src else None
    if not source_header:
        return
    source_text = src.read_text(encoding="utf-8", errors="replace") if src and src.is_file() else None
    store_path = _state_store_path(config)
    store = MigrationStateStore.load(store_path)
    store.record(
        source_header=source_header,
        target_relpath=target_relpath,
        source_text=source_text,
        host_passed=host_passed,
        kernel_passed=kernel_passed,
    )
    store.save(store_path)


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
    host_state = _dimension_state(test_result, "host")
    kernel_state = _dimension_state(test_result, "kernel")
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


def _maybe_build_toolbox(config: Config):
    """启用 model.tools_enabled（且非 mock）时构建模型工具箱；否则返回 None。

    迁移 / 测试迁移 / 测试反馈修复三条链路共用 core.llm.agent_tools.build_toolbox（单一事实源）。
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
