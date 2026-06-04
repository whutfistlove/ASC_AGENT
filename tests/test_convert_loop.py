"""convert 自动闭环（测试失败 -> 回传模型 -> 改正写回 -> 重测）的离线单测。

通过 monkeypatch 掉真正跑 bash 的 _run_operator_tests，专注验证循环编排：
何时进入循环、是否把修复写回仓库、命中通过即停、否则跑满最大轮数。
"""

import argparse
from pathlib import Path

import main
from core.config import Config
from core.model_client import MockModelClient
from core.pipeline import RunResult

TARGET_REL = "libascendcxx/include/ascend/std/__algorithm/min.h"


def _make_config(tmp_path) -> Config:
    # project_root 用真实根（让 skills/ 提示词存在），仅把 accl_repo / output_dir 指到 tmp
    return Config.load(
        None,
        project_root=main.PROJECT_ROOT,
        overrides={
            "paths": {
                "accl_repo": str(tmp_path / "accl"),
                "output_dir": str(tmp_path / "outputs"),
            },
            "repo_verify": {"conda_sh": ""},
        },
    )


def _args(**over):
    base = dict(
        mock=False, dry_run=False, quiet=True, test_dry_run=False,
        prepare_tests_only=False, overwrite_tests=False,
        host_only=False, kernel_only=False, kernel_mode="run_test",
        test_feedback_to_model=True,
        test_feedback_skill="rewrite_fix_from_log_and_test.md",
        max_fix_rounds=3, show_model_io=False,
    )
    base.update(over)
    return argparse.Namespace(**base)


def _seed_target(cfg) -> Path:
    target = Path(cfg.target_repo) / TARGET_REL
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("// broken v0\n", encoding="utf-8")
    return target


def _result() -> RunResult:
    return RunResult(input_path="x.h", target_relpath=TARGET_REL,
                     expected_header_guard="LIBASCENDCXX_INCLUDE_ASCEND_STD___ALGORITHM_MIN_H_")


def test_loop_fixes_then_passes(tmp_path, monkeypatch):
    cfg = _make_config(tmp_path)
    target = _seed_target(cfg)

    calls = {"n": 0}

    def fake_tests(args, config, target_relpath, **kw):
        calls["n"] += 1
        ok = calls["n"] >= 2  # 第一次失败，修复写回后第二次通过
        return {"host_passed": ok, "kernel_passed": ok, "error": "", "skipped": False}

    monkeypatch.setattr(main, "_run_operator_tests", fake_tests)
    # 新契约：失败时模型可改 header(rewritten_code) / host_test_code / kernel_spec 的任意子集。
    # 这里用 rewritten_code（模型最自然的键名），验证别名被正确识别为 header 修复。
    model = MockModelClient(
        responses=['{"root_cause": "operator", "rewritten_code": "// fixed v1\\n", "notes": "fix"}']
    )

    tr = main._run_convert_test_loop(_args(), cfg, model, _result(), write_to_repo=True)

    assert tr["host_passed"] is True and tr["kernel_passed"] is True
    assert target.read_text(encoding="utf-8") == "// fixed v1\n"   # 修复已写回仓库
    assert len(tr["fix_rounds"]) == 1 and tr["fix_rounds"][0]["passed"] is True
    assert tr["fix_rounds"][0]["applied"] == ["header"]
    assert calls["n"] == 2                                          # 初测 + 修复后重测


def test_loop_fixes_test_not_operator(tmp_path, monkeypatch):
    """失败根因在测试时，应改测试（host_test_code）而非算子 header —— 防止 swap 那类被篡改。"""
    cfg = _make_config(tmp_path)
    target = _seed_target(cfg)

    calls = {"n": 0}
    seen = {}

    def fake_tests(args, config, target_relpath, **kw):
        calls["n"] += 1
        seen["artifacts"] = kw.get("test_artifacts")
        ok = calls["n"] >= 2
        return {"host_passed": ok, "kernel_passed": ok, "error": "", "skipped": False}

    monkeypatch.setattr(main, "_run_operator_tests", fake_tests)
    new_host = "static int g_failures = 0;\\nint main(){return g_failures == 0 ? 0 : 1;}\\n"
    model = MockModelClient(
        responses=[f'{{"root_cause": "host_test", "host_test_code": "{new_host}", "notes": "fix test"}}']
    )

    tr = main._run_convert_test_loop(_args(), cfg, model, _result(), write_to_repo=True)

    assert tr["fix_rounds"][0]["applied"] == ["host_test"]
    assert tr["fix_rounds"][0]["passed"] is True
    # 关键：算子 header 未被改动（语义为基准）。
    assert target.read_text(encoding="utf-8") == "// broken v0\n"
    # 修好的 host 测试随 artifacts 传入下一次测试。
    assert seen["artifacts"]["host_test_code"] == new_host.replace("\\n", "\n")


def test_loop_disabled_without_flag(tmp_path, monkeypatch):
    cfg = _make_config(tmp_path)
    _seed_target(cfg)
    monkeypatch.setattr(
        main, "_run_operator_tests",
        lambda *a, **k: {"host_passed": False, "kernel_passed": False, "error": "", "skipped": False},
    )
    model = MockModelClient(responses=[])  # 不应被调用

    tr = main._run_convert_test_loop(_args(test_feedback_to_model=False), cfg, model, _result(), write_to_repo=True)

    assert "fix_rounds" not in tr            # 未进入循环
    assert model.calls == []                 # 模型未被调用


def test_loop_runs_until_max_rounds(tmp_path, monkeypatch):
    cfg = _make_config(tmp_path)
    _seed_target(cfg)
    monkeypatch.setattr(
        main, "_run_operator_tests",
        lambda *a, **k: {"host_passed": False, "kernel_passed": False, "error": "", "skipped": False},
    )
    # 每轮都给一个与上一版不同的 header_code（新契约）
    responses = [f'{{"root_cause": "operator", "header_code": "// v{i}\\n", "notes": "n"}}' for i in range(1, 6)]
    model = MockModelClient(responses=responses)
    result = _result()

    tr = main._run_convert_test_loop(_args(max_fix_rounds=3), cfg, model, result, write_to_repo=True)

    assert len(tr["fix_rounds"]) == 3        # 跑满 3 轮
    assert result.rounds_used == 3
    assert all(r["passed"] is False for r in tr["fix_rounds"])
