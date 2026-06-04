"""单轮修复：基于最新 post-hook 基线 + 最近一次 commit 日志做最小必要修复。

改进：模型调用通过注入的 model_client 完成，便于在 mock 下测试整条修复链路。
"""

from __future__ import annotations

import json
from pathlib import Path

from core.config import Config
from core.model_client import (
    BaseModelClient,
    extract_json_object,
    normalize_generated_text,
)
from core.utils import save_text, call_model_with_io


def build_fix_request(target_relpath: str, expected_header_guard: str,
                      baseline_text: str, commit_log_text: str,
                      test_feedback_text: str = "") -> str:
    test_block = ""
    if test_feedback_text.strip():
        test_block = f"""
【最新 host/kernel 测试反馈】
{test_feedback_text}
"""

    return f"""【目标相对路径 target_relpath】
{target_relpath}

【expected_header_guard】
{expected_header_guard}

【当前 post-hook 基线文件内容】
{baseline_text}

【最近一次 commit / hook 检查日志】
{commit_log_text}
{test_block}

【本轮修复要求】
1. 你只能基于“当前 post-hook 基线文件内容”做最小必要修复。
2. 只修复日志中明确指出的问题；若提供了测试反馈，同时修复测试反馈直接指向的问题。
3. 不要重新迁移整个文件。
4. 不要删除或修改版权头。
5. 不要修改 expected_header_guard。
6. 如果日志只指出 1 个问题，尽量只改与该问题相关的少量行。
7. 如果日志没有提到 include_order，就不要主动重排 include。
8. 不要无关地修改命名空间、宏名、注释、空行、函数实现。
"""


def run_single_fix_from_log(
    config: Config,
    model_client: BaseModelClient,
    target_relpath: str,
    expected_header_guard: str,
    round_index: int,
    commit_log_filename: str,
    prompt_filename: str = "rewrite_fix_from_log.md",
    test_feedback_text: str = "",
    verbose: bool = True,
    show_model_io: bool = False,
) -> Path:
    output_dir = config.output_dir
    baseline_path = output_dir / "post_hook_baseline.h"
    commit_log_path = output_dir / commit_log_filename

    if not baseline_path.exists():
        raise FileNotFoundError(f"找不到 post-hook 基线文件: {baseline_path}")
    if not commit_log_path.exists():
        raise FileNotFoundError(f"找不到 commit 日志: {commit_log_path}")

    baseline_text = baseline_path.read_text(encoding="utf-8")
    commit_log_text = commit_log_path.read_text(encoding="utf-8")

    fix_request_text = build_fix_request(
        target_relpath, expected_header_guard, baseline_text, commit_log_text, test_feedback_text=test_feedback_text
    )

    fix_request_path = output_dir / f"fix_request_round{round_index}.md"
    fix_raw_output_path = output_dir / f"fix_model_raw_output_round{round_index}.md"
    fix_result_json_path = output_dir / f"fix_result_round{round_index}.json"
    fixed_target_path = output_dir / f"fixed_target_round{round_index}.h"
    fix_notes_path = output_dir / f"fix_notes_round{round_index}.md"

    save_text(fix_request_path, fix_request_text)

    prompt_text = config.skill_path(prompt_filename).read_text(encoding="utf-8")
    if verbose:
        print(f"开始调用模型进行第 {round_index} 轮修复...")
    raw = call_model_with_io(
        model_client, stage=f"第 {round_index} 轮修复", system_prompt=prompt_text,
        user_content=fix_request_text, show_io=show_model_io,
    )
    save_text(fix_raw_output_path, raw)

    result = extract_json_object(raw)
    for field in ("rewritten_code", "notes"):
        if field not in result:
            raise ValueError(f"模型输出 JSON 缺少必要字段: {field}")

    rewritten_code = normalize_generated_text(str(result["rewritten_code"]), config.normalize_options)
    notes = str(result["notes"]).strip()

    if rewritten_code.strip() == baseline_text.strip():
        notes += "\n\n[系统提示] 模型未产生与最新 post-hook 基线不同的结果，已保留基线版本。"
        rewritten_code = baseline_text

    result["rewritten_code"] = rewritten_code
    save_text(fix_result_json_path, json.dumps(result, ensure_ascii=False, indent=2))
    save_text(fixed_target_path, rewritten_code)
    save_text(fix_notes_path, notes)

    return fixed_target_path


def run_single_fix_from_test_feedback(
    config: Config,
    model_client: BaseModelClient,
    target_relpath: str,
    expected_header_guard: str,
    commit_log_text: str,
    test_feedback_text: str,
    prompt_filename: str = "rewrite_fix_from_log_and_test.md",
    verbose: bool = True,
    show_model_io: bool = False,
) -> Path:
    output_dir = config.output_dir
    baseline_path = output_dir / "post_hook_baseline.h"
    if not baseline_path.exists():
        raise FileNotFoundError(f"找不到 post-hook 基线文件: {baseline_path}")

    baseline_text = baseline_path.read_text(encoding="utf-8")
    fix_request_text = build_fix_request(
        target_relpath=target_relpath,
        expected_header_guard=expected_header_guard,
        baseline_text=baseline_text,
        commit_log_text=commit_log_text,
        test_feedback_text=test_feedback_text,
    )

    fix_request_path = output_dir / "fix_request_test_feedback.md"
    fix_raw_output_path = output_dir / "fix_model_raw_output_test_feedback.md"
    fix_result_json_path = output_dir / "fix_result_test_feedback.json"
    fixed_target_path = output_dir / "fixed_target_test_feedback.h"
    fix_notes_path = output_dir / "fix_notes_test_feedback.md"

    save_text(fix_request_path, fix_request_text)
    prompt_text = config.skill_path(prompt_filename).read_text(encoding="utf-8")
    if verbose:
        print("开始调用模型基于测试反馈生成修复稿...")
    raw = call_model_with_io(
        model_client, stage="测试反馈修复", system_prompt=prompt_text,
        user_content=fix_request_text, show_io=show_model_io,
    )
    save_text(fix_raw_output_path, raw)

    result = extract_json_object(raw)
    for field in ("rewritten_code", "notes"):
        if field not in result:
            raise ValueError(f"模型输出 JSON 缺少必要字段: {field}")

    rewritten_code = normalize_generated_text(str(result["rewritten_code"]), config.normalize_options)
    notes = str(result["notes"]).strip()

    if rewritten_code.strip() == baseline_text.strip():
        notes += "\n\n[系统提示] 模型未产生与最新 post-hook 基线不同的结果，已保留基线版本。"
        rewritten_code = baseline_text

    result["rewritten_code"] = rewritten_code
    save_text(fix_result_json_path, json.dumps(result, ensure_ascii=False, indent=2))
    save_text(fixed_target_path, rewritten_code)
    save_text(fix_notes_path, notes)
    return fixed_target_path


def run_test_feedback_fix(
    config: Config,
    model_client: BaseModelClient,
    target_relpath: str,
    expected_header_guard: str,
    baseline_text: str,
    test_feedback_text: str,
    round_index: int,
    commit_log_text: str = "(convert 模式：无 commit 日志，仅依据测试反馈修复)",
    prompt_filename: str = "rewrite_fix_from_log_and_test.md",
    verbose: bool = True,
    show_model_io: bool = False,
) -> tuple[Path, str]:
    """迭代版测试反馈修复：以**传入的当前代码** baseline_text 为基线（不读 post-hook 基线），
    结合测试反馈生成一版修复，返回 (写出路径, 修复后代码文本)。

    供 convert 的自动闭环按轮调用：每轮把上一版仓库代码当基线，产出新版用于写回再测。
    """
    output_dir = config.output_dir
    fix_request_text = build_fix_request(
        target_relpath=target_relpath,
        expected_header_guard=expected_header_guard,
        baseline_text=baseline_text,
        commit_log_text=commit_log_text,
        test_feedback_text=test_feedback_text,
    )
    save_text(output_dir / f"fix_request_test_round{round_index}.md", fix_request_text)

    prompt_text = config.skill_path(prompt_filename).read_text(encoding="utf-8")
    if verbose:
        print(f"开始调用模型基于测试反馈生成第 {round_index} 轮修复...")
    raw = call_model_with_io(
        model_client, stage=f"测试反馈修复 第 {round_index} 轮",
        system_prompt=prompt_text, user_content=fix_request_text, show_io=show_model_io,
    )
    save_text(output_dir / f"fix_model_raw_test_round{round_index}.md", raw)

    result = extract_json_object(raw)
    for field in ("rewritten_code", "notes"):
        if field not in result:
            raise ValueError(f"模型输出 JSON 缺少必要字段: {field}")

    rewritten_code = normalize_generated_text(str(result["rewritten_code"]), config.normalize_options)
    notes = str(result["notes"]).strip()
    if rewritten_code.strip() == baseline_text.strip():
        notes += "\n\n[系统提示] 模型未产生与当前代码不同的结果，已保留原版本。"
        rewritten_code = baseline_text

    result["rewritten_code"] = rewritten_code
    save_text(output_dir / f"fix_result_test_round{round_index}.json",
              json.dumps(result, ensure_ascii=False, indent=2))
    fixed_path = output_dir / f"fixed_target_test_round{round_index}.h"
    save_text(fixed_path, rewritten_code)
    save_text(output_dir / f"fix_notes_test_round{round_index}.md", notes)
    return fixed_path, rewritten_code
