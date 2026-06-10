"""P1 单测：带工具的修复链路（离线，用 tool-scripted MockModelClient 驱动）。"""

import json
from pathlib import Path

import pytest

from core.agent_tools import AgentToolbox
from core.config import Config
from core.fix_once import run_test_artifact_fix
from core.model_client import MockModelClient


def _cfg(tmp_path) -> Config:
    (tmp_path / "skills" / "_shared").mkdir(parents=True)
    (tmp_path / "skills" / "fix_tests_from_log.md").write_text("FIX PROMPT", encoding="utf-8")
    return Config.load(
        None,
        project_root=tmp_path,
        overrides={
            "paths": {"output_dir": str(tmp_path / "outputs")},
            "repo_verify": {"conda_sh": ""},
        },
    )


def _toolbox(tmp_path) -> AgentToolbox:
    repo = tmp_path / "accl"
    inc = repo / "asc-stl" / "include" / "asc" / "std"
    inc.mkdir(parents=True)
    (inc / "__config").write_text("#define _ASC_AICORE_FN inline\n", encoding="utf-8")
    return AgentToolbox(repo, tmp_path / "outputs", host_include_dirs=[repo / "asc-stl" / "include"])


def test_fix_invokes_tools_before_answering(tmp_path):
    cfg = _cfg(tmp_path)
    toolbox = _toolbox(tmp_path)

    final = json.dumps({
        "root_cause": "host_test",
        "host_test_code": "#include <cassert>\nint main(){ assert(1); return 0; }",
        "notes": "查阅 __config 后确认宏定义，修正 host 测试。",
    })
    # 模型先取证（读 __config），再返回最终 JSON。
    client = MockModelClient(
        responses=[final],
        tool_script=[{"name": "read_repo_file",
                      "arguments": {"relpath": "asc-stl/include/asc/std/__config"}}],
    )

    out = run_test_artifact_fix(
        config=cfg,
        model_client=client,
        target_relpath="asc-stl/include/asc/std/__algorithm/max.h",
        expected_header_guard="GUARD_H_",
        header_text="// header",
        host_test_text="// host",
        kernel_spec=None,
        test_feedback_text="host_result: FAILED",
        round_index=1,
        verbose=False,
        toolbox=toolbox,
    )

    # 工具确实被调用过（取证），且最终修复被正确解析。
    assert toolbox.call_log and toolbox.call_log[0]["name"] == "read_repo_file"
    assert out["root_cause"] == "host_test"
    assert "host_test_code" in out


def test_fix_without_toolbox_is_single_shot(tmp_path):
    cfg = _cfg(tmp_path)
    final = json.dumps({"root_cause": "kernel_test", "notes": "n",
                        "kernel_spec": {"gm_inputs": 2, "gm_outputs": 1,
                                        "input_init": "h_in0[i]=i;", "element_op_code": "out0_val=in0_val;",
                                        "golden_code": "expected0=in0_ref;"}})
    client = MockModelClient(responses=[final])
    out = run_test_artifact_fix(
        config=cfg, model_client=client,
        target_relpath="asc-stl/include/asc/std/__algorithm/max.h",
        expected_header_guard="GUARD_H_", header_text="// h", host_test_text="// host",
        kernel_spec=None, test_feedback_text="kernel_result: FAILED", round_index=1,
        verbose=False, toolbox=None,
    )
    assert out["root_cause"] == "kernel_test"
    assert "kernel_spec" in out
    # 没传 toolbox，不应触发工具对话
    assert all("tools" not in c for c in client.calls)


def test_tool_calls_are_persisted_for_audit(tmp_path):
    """带工具修复后，本阶段工具调用应落盘成可审计的 tool_calls_*.json。"""
    cfg = _cfg(tmp_path)
    toolbox = _toolbox(tmp_path)
    final = json.dumps({"root_cause": "host_test",
                        "host_test_code": "#include <cassert>\nint main(){assert(1);return 0;}",
                        "notes": "ok"})
    client = MockModelClient(
        responses=[final],
        tool_script=[{"name": "host_syntax_check", "arguments": {"code": "int main(){}"}}],
    )
    run_test_artifact_fix(
        config=cfg, model_client=client,
        target_relpath="asc-stl/include/asc/std/__algorithm/max.h",
        expected_header_guard="G", header_text="// h", host_test_text="// host",
        kernel_spec=None, test_feedback_text="host_result: FAILED", round_index=1,
        verbose=False, toolbox=toolbox,
    )
    audit = json.loads((cfg.output_dir / "tool_calls_fix_round1.json").read_text(encoding="utf-8"))
    assert audit["count"] >= 1
    assert audit["tool_calls"][0]["name"] == "host_syntax_check"
    assert "result_preview" in audit["tool_calls"][0]   # 结果摘要也被记录


def test_fix_with_tools_tolerates_conversational_preamble(tmp_path):
    """带工具时模型最终回答常带前言 + ```json 包裹；非严格抽取应能正确解析（回归 strict 误拒 bug）。"""
    cfg = _cfg(tmp_path)
    toolbox = _toolbox(tmp_path)
    inner = {"root_cause": "host_test",
             "host_test_code": "#include <cassert>\nint main(){assert(1);return 0;}",
             "notes": "查阅后修测试。"}
    final = "Host test passes syntax check. Now I'll produce the final JSON output.\n\n```json\n" \
            + json.dumps(inner) + "\n```"
    client = MockModelClient(
        responses=[final],
        tool_script=[{"name": "host_syntax_check", "arguments": {"code": "int main(){}"}}],
    )
    out = run_test_artifact_fix(
        config=cfg, model_client=client,
        target_relpath="asc-stl/include/asc/std/__algorithm/max.h",
        expected_header_guard="G", header_text="// h", host_test_text="// host",
        kernel_spec=None, test_feedback_text="host_result: FAILED", round_index=1,
        verbose=False, toolbox=toolbox,
    )
    assert out["root_cause"] == "host_test" and "host_test_code" in out


def test_fix_without_tools_keeps_strict_json(tmp_path):
    """不带工具时仍要求严格 JSON：前言 + 包裹应被拒（保持原有契约）。"""
    cfg = _cfg(tmp_path)
    final = "some analysis...\n```json\n" + json.dumps({"root_cause": "env", "notes": "n"}) + "\n```"
    client = MockModelClient(responses=[final])
    with pytest.raises(ValueError):
        run_test_artifact_fix(
            config=cfg, model_client=client,
            target_relpath="asc-stl/include/asc/std/__algorithm/max.h",
            expected_header_guard="G", header_text="// h", host_test_text="// host",
            kernel_spec=None, test_feedback_text="FAILED", round_index=1,
            verbose=False, toolbox=None,
        )
