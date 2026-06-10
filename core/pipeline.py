"""端到端编排。

把 v2 main() 里那一大段流程抽成可注入依赖、可测试的 Pipeline：
    模型初稿 -> 第一次提交(形成 post-hook 基线) -> 多轮修复 -> 通过后自动 push

Pipeline 不直接 import 具体的模型/仓库实现，而是接收符合接口的对象，
因此既能接真实的 ZhipuModelClient + RepoVerifier，
也能在测试/演示里接 MockModelClient + FakeVerifier，完全离线跑通。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable, Optional, Protocol

from core.agent_tools import build_toolbox
from core.best_of_n import best_of_n, score_header_code
from core.config import Config
from core.example_retrieval import select_header_examples
from core.fix_once import run_single_fix_from_log
from core.migration_context import build_migration_context_pack
from core.model_client import (
    BaseModelClient,
    extract_json_object,
    normalize_generated_text,
)
from core.path_mapper import (
    infer_module_hint,
    map_target_relpath,
    expected_guard_from_relpath,
)
from core.utils import save_text, read_text_file, call_model_maybe_tools


SAFE_DEPENDENCY_SKIP_STATUSES = {"host_passed", "kernel_passed", "full_passed"}
DEFERRED_UPSTREAM_SUPPORT_PREFIXES = (
    "__cccl/",
    "__internal/",
    "__support/",
    "detail/",
)


# --------------------------------------------------------------------------- #
# Verifier 接口
# --------------------------------------------------------------------------- #
class Verifier(Protocol):
    def first_commit_verify(self, generated_file_path: Path, target_relpath: str) -> dict: ...
    def repair_commit_verify(self, generated_file_path: Path, target_relpath: str, round_index: int) -> dict: ...
    def push(self, branch_name: str) -> dict: ...


# --------------------------------------------------------------------------- #
# 运行结果
# --------------------------------------------------------------------------- #
@dataclass
class RunResult:
    input_path: str
    target_relpath: str = ""
    expected_header_guard: str = ""
    module_hint: str = ""
    converted: bool = False          # 模型初稿是否成功生成
    baseline_formed: bool = False    # 是否形成 post-hook 基线
    commit_passed: bool = False      # 是否有一轮 commit 通过
    rounds_used: int = 0             # 进行了几轮修复
    pushed: bool = False
    branch_name: str = ""
    test_result: dict = field(default_factory=dict)
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DependencyAwareHeaderResult:
    source_header: str
    input_path: str
    target_relpath: str = ""
    action: str = ""
    reason: str = ""
    status: str = ""
    run_result: dict = field(default_factory=dict)
    test_result: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DependencyAwareRunResult:
    entry_header: str
    ordered_headers: list[str] = field(default_factory=list)
    rewritten_headers: list[str] = field(default_factory=list)
    skipped_headers: list[str] = field(default_factory=list)
    failed_test_headers: list[str] = field(default_factory=list)
    items: list[DependencyAwareHeaderResult] = field(default_factory=list)
    complete: bool = False
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "complete": self.complete,
            "entry_header": self.entry_header,
            "error": self.error,
            "items": [item.to_dict() for item in self.items],
            "ordered_headers": list(self.ordered_headers),
            "rewritten_headers": list(self.rewritten_headers),
            "skipped_headers": list(self.skipped_headers),
            "failed_test_headers": list(self.failed_test_headers),
        }


def _dep_map(dep_graph) -> dict[str, list[str]]:
    return {entry.header: list(entry.dependencies) for entry in dep_graph.graph}


def _dependency_order_including_entry(entry_header: str, dep_graph) -> list[str]:
    dep_map = _dep_map(dep_graph)
    if entry_header not in dep_map:
        raise ValueError(f"entry header not found in dependency graph: {entry_header}")

    reachable: set[str] = {entry_header}

    def visit(node: str) -> None:
        for dep in dep_map.get(node, []):
            if dep in reachable:
                continue
            reachable.add(dep)
            visit(dep)

    visit(entry_header)
    order_index = {header: idx for idx, header in enumerate(dep_graph.topological_order)}
    return sorted(reachable, key=lambda header: (order_index.get(header, 10**9), header))


def _manual_bootstrap_cover(header: str, config: Config) -> str | None:
    if header != "detail/__config":
        return None
    target_relpath = str(Path(config.target_repo_prefix) / "__config")
    if (Path(config.target_repo) / target_relpath).exists():
        return target_relpath
    return None


def _deferred_support_reason(header: str, config: Config) -> str | None:
    covered_by = _manual_bootstrap_cover(header, config)
    if covered_by:
        return f"covered_by_bootstrap_manual:{covered_by}"
    if header.startswith(DEFERRED_UPSTREAM_SUPPORT_PREFIXES):
        return "deferred_upstream_support_only"
    return None


# --------------------------------------------------------------------------- #
# Pipeline
# --------------------------------------------------------------------------- #
class Pipeline:
    def __init__(self, config: Config, model_client: BaseModelClient,
                 verifier: Verifier, verbose: bool = True, show_model_io: bool = False,
                 toolbox=None):
        self.config = config
        self.model = model_client
        self.verifier = verifier
        self.verbose = verbose
        self.show_model_io = show_model_io
        # 显式注入优先（便于离线测试 agentic 生成路径）；否则按配置构建（默认关闭→None）。
        self.toolbox = toolbox

    def _log(self, *args) -> None:
        if self.verbose:
            print(*args)

    def _resolve_toolbox(self):
        return self.toolbox if self.toolbox is not None else build_toolbox(self.config)

    # ---- 构造初始改写请求 ---- #
    def _build_initial_request(self, input_path: Path, source_text: str,
                               module_hint: str, target_relpath: str, guard: str,
                               examples: list[tuple[str, str]],
                               context_pack: Optional[dict] = None) -> str:
        head = f"""【当前任务文件路径】
{input_path}

【module_hint】
{module_hint}

【目标相对路径 target_relpath】
{target_relpath}

【expected_header_guard】
{guard}

【当前待改写的 CCCL 文件内容】
{source_text}
"""
        if context_pack is not None:
            head += (
                "\n【Node 11 bounded migration context pack】\n"
                + json.dumps(context_pack, ensure_ascii=False, indent=2, sort_keys=True)
                + "\n"
            )
        blocks = []
        for i, (cccl, accl) in enumerate(examples, 1):
            blocks.append(
                f"====================\n"
                f"【成功示例 {i} - 原始 CCCL 文件内容】\n{read_text_file(cccl)}\n\n"
                f"【成功示例 {i} - 正确 ACCL 文件内容】\n{read_text_file(accl)}\n"
            )
        return head + "\n" + "\n".join(blocks)

    def run(self, input_path: Path) -> RunResult:
        input_path = Path(input_path).resolve()
        result = RunResult(input_path=str(input_path))
        try:
            return self._run_inner(input_path, result)
        except Exception as exc:  # 单文件失败不应中断批处理
            result.error = f"{type(exc).__name__}: {exc}"
            self._log(f"[error] {result.error}")
            return result

    def _rewrite(self, input_path: Path, result: RunResult, context_pack: Optional[dict] = None) -> Path:
        """模型初稿：读源文件 -> 推导路径/guard -> 调模型 -> 落盘 rewritten_target.h。

        返回 outputs/rewritten_target.h 路径，并把映射信息写入 result。
        run() 与 convert_only() 共用这一段。
        """
        cfg = self.config
        out = cfg.output_dir

        if not input_path.exists():
            raise FileNotFoundError(f"输入文件不存在: {input_path}")
        source_text = input_path.read_text(encoding="utf-8")

        module_hint = infer_module_hint(input_path, cfg.source_repo_prefix, cfg.module_hint_fallback)
        target_relpath = map_target_relpath(
            input_path, cfg.source_repo_prefix, cfg.target_repo_prefix, cfg.segment_substitutions
        )
        guard = expected_guard_from_relpath(target_relpath)

        result.module_hint = module_hint
        result.target_relpath = target_relpath
        result.expected_header_guard = guard
        self._log(f"module_hint={module_hint}  target_relpath={target_relpath}  guard={guard}")

        # ---- 模型初稿 ---- #
        # few-shot 按算子相关度从 examples/ 检索（示例库越大越受益；默认开，可关回固定顺序）。
        examples = select_header_examples(
            cfg, target_relpath=target_relpath, source_text=source_text,
            k=cfg.few_shot_top_k, enabled=cfg.examples_retrieval_enabled,
            exclude_self=True,  # 迁 X 不拿 X 自己的答案当示例（防泄漏）
        )
        request_text = self._build_initial_request(
            input_path, source_text, module_hint, target_relpath, guard, examples, context_pack
        )
        save_text(out / "model_request.md", request_text)

        prompt = cfg.read_skill("rewrite_initial.md")
        toolbox = self._resolve_toolbox()
        self._log(
            "开始调用模型进行初始改写..."
            + ("（带工具：可读 sibling 头 / grep 符号 / 落盘前自检）" if toolbox else "")
        )
        # 启用工具后，模型可在出初稿前读 sibling 头、查 __config 宏、g++ 自检——
        # 把「蒙眼单发」变成「可取证 + 可自验证」的生成，直接减少后续修复往返。
        def _draft_once() -> str:
            return call_model_maybe_tools(
                self.model, stage="初始改写", system_prompt=prompt,
                user_content=request_text, show_io=self.show_model_io,
                toolbox=toolbox, max_tool_rounds=cfg.model_max_tool_rounds,
                tool_log_tag="rewrite",
            )

        def _parse_draft(text: str) -> dict:
            d = extract_json_object(text)
            for f in ("file_type", "rewritten_code", "notes"):
                if f not in d:
                    raise ValueError(f"模型输出 JSON 缺少必要字段: {f}")
            d["rewritten_code"] = normalize_generated_text(str(d["rewritten_code"]), cfg.normalize_options)
            return d

        # best-of-N：draft_samples>1 时多采样，按 guard/指令配平结构分择优（默认 1=单发）。
        if cfg.draft_samples > 1:
            data, raw, scores = best_of_n(
                _draft_once, _parse_draft,
                lambda d: score_header_code(d["rewritten_code"], guard),
                n=cfg.draft_samples,
            )
            self._log(f"best-of-{cfg.draft_samples} 初稿择优：scores={scores}")
        else:
            raw = _draft_once()
            data = _parse_draft(raw)
        save_text(out / "model_raw_output.md", raw)

        rewritten_code = data["rewritten_code"]
        rewritten_target = out / "rewritten_target.h"
        save_text(out / "rewrite_result.json", json.dumps(data, ensure_ascii=False, indent=2))
        save_text(rewritten_target, rewritten_code)
        save_text(out / "rewrite_notes.md", str(data["notes"]).strip())
        result.converted = True
        return rewritten_target

    def convert_only(self, input_path: Path, write_to_repo: bool = True) -> RunResult:
        """只做「生成」：模型转换 + （可选）把结果直接写入目标仓库，不走 git/commit。

        用于「提交暂时忽略」的全流程：生成 -> 写入 ACCL 仓库 -> 跑 host/kernel 测试。
        """
        input_path = Path(input_path).resolve()
        result = RunResult(input_path=str(input_path))
        try:
            rewritten_target = self._rewrite(input_path, result)
            if write_to_repo:
                target_file = Path(self.config.target_repo) / result.target_relpath
                target_file.parent.mkdir(parents=True, exist_ok=True)
                target_file.write_text(
                    rewritten_target.read_text(encoding="utf-8"), encoding="utf-8"
                )
                self._log(f"已写入目标文件: {target_file}")
        except Exception as exc:
            result.error = f"{type(exc).__name__}: {exc}"
            self._log(f"[error] {result.error}")
        return result

    def convert_dependency_closure(
        self,
        *,
        entry_header: str,
        inventory,
        test_index,
        dep_graph,
        status_report,
        write_to_repo: bool = True,
        skip_statuses: Optional[set[str]] = None,
        plan_only: bool = False,
        on_rewritten: Optional[Callable[[RunResult], tuple[bool, dict]]] = None,
        stop_on_test_failure: bool = True,
    ) -> DependencyAwareRunResult:
        """Rewrite one entry header after its missing dependency closure.

        The order is leaf-first according to `core.dep_graph`. Headers that
        already exist in the ACCL target and have validation evidence are
        skipped. Every actual rewrite receives a fresh Node 11 context pack for
        the header being rewritten. With `plan_only=True`, this only reports the
        ordered skip/rewrite plan and performs no model calls or writes.

        If `on_rewritten` is given, it is invoked right after each header is
        rewritten (leaf-first), receiving that header's `RunResult` and returning
        `(is_failure, test_result)`. The `test_result` is attached to the report
        item; when `is_failure` is true the header is recorded in
        `failed_test_headers`, and if `stop_on_test_failure` is true the closure
        stops before rewriting any dependents.
        """
        skip_statuses = set(skip_statuses or SAFE_DEPENDENCY_SKIP_STATUSES)
        result = DependencyAwareRunResult(entry_header=entry_header)
        status_by_header = {entry.source_header: entry for entry in status_report.headers}
        header_root = Path(inventory.header_root)

        try:
            ordered_headers = _dependency_order_including_entry(entry_header, dep_graph)
        except Exception as exc:
            result.error = f"{type(exc).__name__}: {exc}"
            self._log(f"[error] {result.error}")
            return result

        result.ordered_headers = ordered_headers
        self._log(
            f"dependency-aware order for {entry_header}: "
            + " -> ".join(ordered_headers)
        )

        for header in ordered_headers:
            status = status_by_header.get(header)
            input_path = header_root / header
            target_relpath = status.target_relpath if status else ""
            status_value = status.status if status else ""
            is_entry = header == entry_header
            if status and status.target_exists and status.status in skip_statuses:
                item = DependencyAwareHeaderResult(
                    source_header=header,
                    input_path=str(input_path),
                    target_relpath=status.target_relpath,
                    action="would_skip" if plan_only else "skipped",
                    reason=f"target_exists_with_safe_status:{status.status}",
                    status=status.status,
                )
                result.items.append(item)
                result.skipped_headers.append(header)
                self._log(f"[skip] {header}: {item.reason}")
                continue
            deferred_reason = None if is_entry else _deferred_support_reason(header, self.config)
            if deferred_reason:
                item = DependencyAwareHeaderResult(
                    source_header=header,
                    input_path=str(input_path),
                    target_relpath=target_relpath,
                    action="would_skip" if plan_only else "skipped",
                    reason=deferred_reason,
                    status=status_value,
                )
                result.items.append(item)
                result.skipped_headers.append(header)
                self._log(f"[skip] {header}: {item.reason}")
                continue
            if plan_only:
                item = DependencyAwareHeaderResult(
                    source_header=header,
                    input_path=str(input_path),
                    target_relpath=target_relpath,
                    action="would_rewrite",
                    reason="missing_or_not_safely_validated",
                    status=status_value,
                )
                result.items.append(item)
                continue

            pack = build_migration_context_pack(
                entry_header=header,
                inventory=inventory,
                test_index=test_index,
                dep_graph=dep_graph,
                status_report=status_report,
                target_repo=self.config.target_repo,
                examples_root=self.config.project_root / "examples",
            )
            run_result = RunResult(input_path=str(input_path))
            try:
                rewritten_target = self._rewrite(input_path, run_result, context_pack=pack)
                if write_to_repo:
                    target_file = Path(self.config.target_repo) / run_result.target_relpath
                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    target_file.write_text(
                        rewritten_target.read_text(encoding="utf-8"), encoding="utf-8"
                    )
                    self._log(f"已写入目标文件: {target_file}")
                item = DependencyAwareHeaderResult(
                    source_header=header,
                    input_path=str(input_path),
                    target_relpath=run_result.target_relpath,
                    action="rewritten",
                    reason="dependency_closure_rewrite",
                    status=status_value,
                    run_result=run_result.to_dict(),
                )
                result.items.append(item)
                result.rewritten_headers.append(header)
                if on_rewritten is not None:
                    try:
                        is_failure, test_result = on_rewritten(run_result)
                    except Exception as cb_exc:  # 测试回调自身异常不应伪装成改写失败
                        is_failure = True
                        test_result = {"error": f"on_rewritten failed: {type(cb_exc).__name__}: {cb_exc}"}
                        self._log(f"[test-error] {header}: {test_result['error']}")
                    item.test_result = test_result or {}
                    if is_failure:
                        result.failed_test_headers.append(header)
                        if stop_on_test_failure:
                            result.error = f"{header}: host/kernel 测试失败（默认失败即停）"
                            self._log(f"[test-fail] {result.error}")
                            return result
            except Exception as exc:
                run_result.error = f"{type(exc).__name__}: {exc}"
                item = DependencyAwareHeaderResult(
                    source_header=header,
                    input_path=str(input_path),
                    target_relpath=target_relpath,
                    action="failed",
                    reason=run_result.error,
                    status=status_value,
                    run_result=run_result.to_dict(),
                )
                result.items.append(item)
                result.error = f"{header}: {run_result.error}"
                self._log(f"[error] {result.error}")
                return result

        result.complete = True
        return result

    def _run_inner(self, input_path: Path, result: RunResult) -> RunResult:
        cfg = self.config
        out = cfg.output_dir

        self._rewrite(input_path, result)
        target_relpath = result.target_relpath
        guard = result.expected_header_guard
        rewritten_target = out / "rewritten_target.h"

        # ---- 第一次提交：形成 post-hook 基线 ---- #
        self._log("执行第一次 repo verify（形成 post-hook 基线）...")
        verify = self.verifier.first_commit_verify(rewritten_target, target_relpath)
        result.branch_name = verify.get("branch_name", "")
        result.baseline_formed = verify.get("post_hook_baseline_saved", False)

        if not result.baseline_formed:
            self._log("未形成 post-hook 基线，停止后续修复。")
            return result

        if verify.get("commit_ok", False):
            return self._do_push(result)

        # ---- 多轮修复 ---- #
        max_rounds = cfg.max_fix_rounds
        current_style_passed = verify.get("style_passed", False)
        current_commit_log = "git_commit.log"

        for r in range(1, max_rounds + 1):
            result.rounds_used = r
            self._log(f"==== 第 {r}/{max_rounds} 轮修复 ====")

            if current_style_passed:
                # 只差版权头之类、style 已过：直接拿最新基线重提，不再调用模型
                fixed_target = out / "post_hook_baseline.h"
            else:
                fixed_target = run_single_fix_from_log(
                    config=cfg,
                    model_client=self.model,
                    target_relpath=target_relpath,
                    expected_header_guard=guard,
                    round_index=r,
                    commit_log_filename=current_commit_log,
                    verbose=self.verbose,
                    show_model_io=self.show_model_io,
                )

            round_result = self.verifier.repair_commit_verify(fixed_target, target_relpath, r)
            if round_result.get("commit_ok", False):
                result.commit_passed = True
                return self._do_push(result)

            current_style_passed = round_result.get("style_passed", False)
            current_commit_log = f"git_commit_round{r}.log"

        self._log(f"已达到最大修复轮数 {max_rounds}，仍未通过。")
        return result

    def _do_push(self, result: RunResult) -> RunResult:
        result.commit_passed = True
        self._log("commit 已通过，开始自动 push...")
        push = self.verifier.push(result.branch_name)
        result.pushed = push.get("push_ok", False)
        return result


# --------------------------------------------------------------------------- #
# FakeVerifier：离线演示 / 测试用，模拟 hook 行为与多轮收敛
# --------------------------------------------------------------------------- #
_FAKE_LICENSE_HEADER = (
    "/******************************************************************************\n"
    " * Copyright (c) 2026 Example Group. All Rights Reserved.\n"
    " * Licensed under the Apache License, Version 2.0 (the \"License\");\n"
    " *****************************************************************************/\n"
)


class FakeVerifier:
    """模拟真实提交检查：

    - 第一次提交：模拟 hook 自动补版权头，保存 post_hook_baseline.h 与 git_commit.log，
      license 视为通过；style 是否通过取决于 rounds_to_pass。
    - rounds_to_pass=0：第一次提交即整体通过。
    - rounds_to_pass=k(>0)：前 k 轮 style 不过、第 k 轮修复后通过。
    """

    def __init__(self, config: Config, rounds_to_pass: int = 0, verbose: bool = False):
        self.config = config
        self.rounds_to_pass = rounds_to_pass
        self.verbose = verbose
        self._out = config.output_dir

    def _checks_log(self, license_ok: bool, style_ok: bool) -> str:
        lines = []
        for c in self.config.repo_verify["checks"]:
            ok = license_ok if c["name"] == "license" else style_ok
            # 用每条 check 的 pattern 反推一段“能被匹配/不被匹配”的日志文案
            label = "Add Apache 2.0 license header" if c["name"] == "license" \
                else "CANN code style check (clang-format + cpplint)"
            lines.append(f"{label} {'Passed' if ok else 'Failed'}")
        return "\n".join(lines) + "\n"

    def _save_baseline(self, content: str, extra_name: str) -> str:
        baseline_path = self._out / "post_hook_baseline.h"
        save_text(baseline_path, content)
        save_text(self._out / extra_name, content)
        return str(baseline_path)

    def first_commit_verify(self, generated_file_path: Path, target_relpath: str) -> dict:
        content = Path(generated_file_path).read_text(encoding="utf-8")
        baselined = _FAKE_LICENSE_HEADER + "\n" + content  # 模拟 hook 补头
        baseline_path = self._save_baseline(baselined, "post_hook_baseline_round0.h")

        style_ok = self.rounds_to_pass == 0
        log = self._checks_log(license_ok=True, style_ok=style_ok)
        save_text(self._out / "git_commit.log", log)

        return {
            "branch_name": "feature/ai-fake-branch",
            "post_hook_baseline_saved": True,
            "post_hook_baseline_path": baseline_path,
            "style_passed": style_ok,
            "commit_ok": style_ok,
            "checks": {"license": True, "style": style_ok},
        }

    def repair_commit_verify(self, generated_file_path: Path, target_relpath: str, round_index: int) -> dict:
        content = Path(generated_file_path).read_text(encoding="utf-8")
        # 修复后内容若没补头，模拟 hook 仍保证有头
        if "Apache License" not in content:
            content = _FAKE_LICENSE_HEADER + "\n" + content
        self._save_baseline(content, f"post_hook_baseline_round{round_index}.h")

        style_ok = round_index >= self.rounds_to_pass
        log = self._checks_log(license_ok=True, style_ok=style_ok)
        save_text(self._out / f"git_commit_round{round_index}.log", log)

        return {
            "round_index": round_index,
            "style_passed": style_ok,
            "commit_ok": style_ok,
            "checks": {"license": True, "style": style_ok},
            "post_hook_baseline_saved": True,
        }

    def push(self, branch_name: str) -> dict:
        save_text(self._out / "git_push.log", f"[fake] pushed {branch_name}\n")
        return {"branch_name": branch_name, "push_ok": True}
