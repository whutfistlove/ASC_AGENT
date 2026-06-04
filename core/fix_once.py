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
from core.test_migrator import validate_host_test_code, validate_kernel_spec
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


def build_test_artifact_fix_request(
    *,
    target_relpath: str,
    expected_header_guard: str,
    header_text: str,
    host_test_text: str,
    kernel_spec_json: str,
    test_feedback_text: str,
) -> str:
    return f"""【目标相对路径 target_relpath】
{target_relpath}

【expected_header_guard】
{expected_header_guard}

【当前 ACCL 算子头文件（header_code 基线）】
{header_text}

【当前 ACCL host 测试（host_test_code 基线）】
{host_test_text}

【当前 kernel_spec(JSON) 基线】
{kernel_spec_json}

【最新 host/kernel 测试反馈】
{test_feedback_text}

【本轮修复要求】
1. 先判定失败根因：算子(operator) / host 测试(host_test) / kernel 测试(kernel_test)。
2. CCCL/ACCL 算子语义是基准：若失败因测试本身写错（如把 void/原地算子当二元返回值、
   把右值绑定到非 const 左值引用、把 void 赋给 float），就改测试，绝不为迁就测试而
   改算子的签名/返回类型/语义。
3. 只返回需要改动的件：header_code / host_test_code / kernel_spec 任意子集；
   不需要改的件请省略或置 null。
4. kernel_spec 可使用 1~8 个 GM 输入和 1~8 个 GM 输出：gm_inputs / gm_outputs /
   input_init / element_op_code / golden_code。多输出时 element_op_code 应给
   out0_val...outM_val 赋值，golden_code 应给 expected0...expectedM 赋值；旧的
   z_val / expected 仍等价于 out0_val / expected0。
5. kernel_spec 的 golden_code 必须是独立参考实现，禁止调用 ascend::std::*。
6. 若改 header_code：保持 expected_header_guard 与版权头不变，做最小必要改动。
7. 若返回 host_test_code：必须让任一用例失败时进程返回非零（例如累计 g_failures，
   最终 return g_failures == 0 ? 0 : 1），不能只打印 FAIL 后 return 0。
"""


def _optional_text_field(data: dict, *names: str) -> str | None:
    """读取可省略/可为 null 的模型文本字段；null/空串表示不改。"""
    for name in names:
        if name not in data:
            continue
        value = data[name]
        if value is None:
            continue
        if not isinstance(value, str):
            raise ValueError(f"模型输出字段 {name} 必须是字符串或 null")
        if value.strip():
            return value
    return None


def run_test_artifact_fix(
    config: Config,
    model_client: BaseModelClient,
    *,
    target_relpath: str,
    expected_header_guard: str,
    header_text: str,
    host_test_text: str,
    kernel_spec: dict | None,
    test_feedback_text: str,
    round_index: int,
    prompt_filename: str = "fix_tests_from_log.md",
    verbose: bool = True,
    show_model_io: bool = False,
) -> dict:
    """测试反馈修复（可同时改 header / host 测试 / kernel_spec）。

    返回字典，仅包含模型本轮决定改动的件（缺省字段表示该件保持不变）：
        {"header_code"?, "host_test_code"?, "kernel_spec"?, "root_cause", "notes"}
    """
    output_dir = config.output_dir
    spec_json = (
        json.dumps(kernel_spec, ensure_ascii=False, indent=2)
        if kernel_spec
        else "(无 kernel_spec：kernel 测试当前使用内置模板)"
    )
    request_text = build_test_artifact_fix_request(
        target_relpath=target_relpath,
        expected_header_guard=expected_header_guard,
        header_text=header_text,
        host_test_text=host_test_text or "(无 host 测试基线)",
        kernel_spec_json=spec_json,
        test_feedback_text=test_feedback_text,
    )
    save_text(output_dir / f"fix_request_test_round{round_index}.md", request_text)

    prompt_text = config.skill_path(prompt_filename).read_text(encoding="utf-8")
    if verbose:
        print(f"开始调用模型基于测试反馈生成第 {round_index} 轮修复（header/测试）...")
    raw = call_model_with_io(
        model_client, stage=f"测试反馈修复 第 {round_index} 轮",
        system_prompt=prompt_text, user_content=request_text, show_io=show_model_io,
    )
    save_text(output_dir / f"fix_model_raw_test_round{round_index}.md", raw)

    data = extract_json_object(raw, strict=True)
    for field in ("root_cause", "notes"):
        if field not in data:
            raise ValueError(f"模型输出 JSON 缺少必要字段: {field}")
        if not isinstance(data[field], str):
            raise ValueError(f"模型输出字段 {field} 必须是字符串")

    out: dict = {
        "root_cause": data["root_cause"].strip(),
        "notes": data["notes"].strip(),
    }
    # header 既接受 header_code，也接受 rewritten_code（本仓库其它提示词通用的键名，
    # 模型很自然地会用它来回传修好的算子头）。
    header_code = _optional_text_field(data, "header_code", "rewritten_code")
    if header_code:
        out["header_code"] = normalize_generated_text(header_code, config.normalize_options)

    host_code = _optional_text_field(data, "host_test_code")
    if host_code:
        out["host_test_code"] = validate_host_test_code(host_code)

    if data.get("kernel_spec") is not None and not isinstance(data.get("kernel_spec"), dict):
        raise ValueError("模型输出字段 kernel_spec 必须是对象或 null")
    if isinstance(data.get("kernel_spec"), dict) and data["kernel_spec"]:
        try:
            out["kernel_spec"] = validate_kernel_spec(data["kernel_spec"])
        except ValueError:
            pass  # 槽位不全的 kernel_spec 忽略，保持上一版

    save_text(output_dir / f"fix_result_test_round{round_index}.json",
              json.dumps(out, ensure_ascii=False, indent=2))
    save_text(output_dir / f"fix_notes_test_round{round_index}.md", out["notes"])
    return out
