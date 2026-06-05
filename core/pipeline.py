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
from typing import Optional, Protocol

from core.config import Config
from core.fix_once import run_single_fix_from_log
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
from core.utils import save_text, read_text_file, call_model_with_io


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


# --------------------------------------------------------------------------- #
# Pipeline
# --------------------------------------------------------------------------- #
class Pipeline:
    def __init__(self, config: Config, model_client: BaseModelClient,
                 verifier: Verifier, verbose: bool = True, show_model_io: bool = False):
        self.config = config
        self.model = model_client
        self.verifier = verifier
        self.verbose = verbose
        self.show_model_io = show_model_io

    def _log(self, *args) -> None:
        if self.verbose:
            print(*args)

    # ---- 构造初始改写请求 ---- #
    def _build_initial_request(self, input_path: Path, source_text: str,
                               module_hint: str, target_relpath: str, guard: str) -> str:
        ex = self.config.example_paths()
        e1c, e1a = ex["example_1"]["cccl"], ex["example_1"]["accl"]
        e2c, e2a = ex["example_2"]["cccl"], ex["example_2"]["accl"]
        return f"""【当前任务文件路径】
{input_path}

【module_hint】
{module_hint}

【目标相对路径 target_relpath】
{target_relpath}

【expected_header_guard】
{guard}

【当前待改写的 CCCL 文件内容】
{source_text}

====================
【成功示例 1 - 原始 CCCL 文件内容】
{read_text_file(e1c)}

【成功示例 1 - 正确 ACCL 文件内容】
{read_text_file(e1a)}

====================
【成功示例 2 - 原始 CCCL 文件内容】
{read_text_file(e2c)}

【成功示例 2 - 正确 ACCL 文件内容】
{read_text_file(e2a)}
"""

    def run(self, input_path: Path) -> RunResult:
        input_path = Path(input_path).resolve()
        result = RunResult(input_path=str(input_path))
        try:
            return self._run_inner(input_path, result)
        except Exception as exc:  # 单文件失败不应中断批处理
            result.error = f"{type(exc).__name__}: {exc}"
            self._log(f"[error] {result.error}")
            return result

    def _rewrite(self, input_path: Path, result: RunResult) -> Path:
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
        request_text = self._build_initial_request(input_path, source_text, module_hint, target_relpath, guard)
        save_text(out / "model_request.md", request_text)

        prompt = cfg.read_skill("rewrite_initial.md")
        self._log("开始调用模型进行初始改写...")
        raw = call_model_with_io(
            self.model, stage="初始改写", system_prompt=prompt,
            user_content=request_text, show_io=self.show_model_io,
        )
        save_text(out / "model_raw_output.md", raw)

        data = extract_json_object(raw)
        for f in ("file_type", "rewritten_code", "notes"):
            if f not in data:
                raise ValueError(f"模型输出 JSON 缺少必要字段: {f}")

        rewritten_code = normalize_generated_text(str(data["rewritten_code"]), cfg.normalize_options)
        data["rewritten_code"] = rewritten_code
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
