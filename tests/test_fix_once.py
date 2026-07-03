"""fix_once 单测：请求构造与测试产物修复契约。"""

import json

import pytest

import main
from core.common.config import Config
from core.llm.model_client import MockModelClient
from core.migration.fix_once import build_fix_request, run_test_artifact_fix


def _cfg(tmp_path) -> Config:
    return Config.load(
        None,
        project_root=main.PROJECT_ROOT,
        overrides={"paths": {"output_dir": str(tmp_path / "outputs")}, "repo_verify": {"conda_sh": ""}},
    )


def test_build_fix_request_without_test_feedback():
    text = build_fix_request(
        target_relpath="asc-stl/include/asc/std/__algorithm/max.h",
        expected_header_guard="G_",
        baseline_text="baseline",
        commit_log_text="commit log",
    )
    assert "【最新 host/kernel 测试反馈】" not in text
    assert "commit log" in text


def test_build_fix_request_with_test_feedback():
    text = build_fix_request(
        target_relpath="asc-stl/include/asc/std/__algorithm/max.h",
        expected_header_guard="G_",
        baseline_text="baseline",
        commit_log_text="commit log",
        test_feedback_text="host failed at line 1",
    )
    assert "【最新 host/kernel 测试反馈】" in text
    assert "host failed at line 1" in text


def test_test_artifact_fix_ignores_json_null_host_test_code(tmp_path):
    cfg = _cfg(tmp_path)
    model = MockModelClient(
        responses=[
            json.dumps(
                {
                    "root_cause": "operator",
                    "rewritten_code": "// fixed\n",
                    "host_test_code": None,
                    "kernel_spec": None,
                    "notes": "header only",
                }
            )
        ]
    )

    out = run_test_artifact_fix(
        cfg,
        model,
        target_relpath="asc-stl/include/asc/std/__algorithm/minmax.h",
        expected_header_guard="G_",
        header_text="// broken\n",
        host_test_text="// previous host\n",
        kernel_spec=None,
        test_feedback_text="compile failed",
        round_index=1,
        verbose=False,
    )

    assert out["header_code"] == "// fixed\n"
    assert "host_test_code" not in out
    saved = json.loads((cfg.fix_output_dir / "fix_result_test_round1.json").read_text(encoding="utf-8"))
    assert "host_test_code" not in saved


def test_test_artifact_fix_rejects_non_json_extra_text(tmp_path):
    cfg = _cfg(tmp_path)
    raw = '{"root_cause":"operator","rewritten_code":"// fixed\\n","notes":"n"}'
    model = MockModelClient(responses=["先分析一下\n" + raw])

    with pytest.raises(ValueError, match="单个 JSON 对象"):
        run_test_artifact_fix(
            cfg,
            model,
            target_relpath="asc-stl/include/asc/std/__algorithm/minmax.h",
            expected_header_guard="G_",
            header_text="// broken\n",
            host_test_text="// previous host\n",
            kernel_spec=None,
            test_feedback_text="compile failed",
            round_index=1,
            verbose=False,
        )


def test_test_artifact_fix_rejects_host_test_that_always_returns_zero(tmp_path):
    cfg = _cfg(tmp_path)
    model = MockModelClient(
        responses=[
            json.dumps(
                {
                    "root_cause": "host_test",
                    "host_test_code": (
                        '#include "asc/std/__algorithm/minmax.h"\n'
                        "int main(){ bool pass = false; return 0; }\n"
                    ),
                    "notes": "bad test",
                }
            )
        ]
    )

    with pytest.raises(ValueError, match="返回非零"):
        run_test_artifact_fix(
            cfg,
            model,
            target_relpath="asc-stl/include/asc/std/__algorithm/minmax.h",
            expected_header_guard="G_",
            header_text="// header\n",
            host_test_text="// previous host\n",
            kernel_spec=None,
            test_feedback_text="host failed",
            round_index=1,
            verbose=False,
        )
