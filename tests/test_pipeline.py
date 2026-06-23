"""Pipeline 端到端集成测试（mock 模型 + 假提交检查，完全离线）。"""

from pathlib import Path

import pytest

from core.common.config import Config
from core.llm.model_client import MockModelClient
from core.migration.pipeline import FakeVerifier, Pipeline


def _make_config(tmp_path) -> Config:
    """在 tmp_path 内搭一个最小可运行项目：examples + skills + 输入文件。"""
    proj = tmp_path
    (proj / "skills").mkdir()
    (proj / "skills" / "rewrite_initial.md").write_text("initial prompt", encoding="utf-8")
    (proj / "skills" / "rewrite_fix_from_log_and_test.md").write_text("fix prompt", encoding="utf-8")

    ex = proj / "examples" / "headers"
    ex.mkdir(parents=True)
    for n in ("max.cccl.h", "max.accl.h", "os.cccl.h", "os.accl.h"):
        (ex / n).write_text(f"// {n}\n", encoding="utf-8")

    cfg = Config.load(None, project_root=proj, overrides={"model": {"provider": "mock"}})
    return cfg


def _make_input(tmp_path) -> Path:
    p = tmp_path / "libcudacxx" / "include" / "cuda" / "std" / "__cccl" / "os.h"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("#ifndef __CCCL_OS_H\n#define __CCCL_OS_H\n#endif // __CCCL_OS_H\n", encoding="utf-8")
    return p


def test_pipeline_passes_on_first_commit(tmp_path):
    cfg = _make_config(tmp_path)
    inp = _make_input(tmp_path)
    pipeline = Pipeline(cfg, MockModelClient(), FakeVerifier(cfg, rounds_to_pass=0), verbose=False)

    result = pipeline.run(inp)

    assert result.converted is True
    assert result.baseline_formed is True
    assert result.commit_passed is True
    assert result.pushed is True
    assert result.rounds_used == 0
    # 目标 guard 应已应用 __cccl -> __asc 段替换
    assert result.expected_header_guard == "ASC_STL_INCLUDE_ASC_STD___ASC_OS_H_"
    assert (cfg.output_dir / "rewritten_target.h").exists()
    assert (cfg.output_dir / "git_push.log").exists()


def test_pipeline_converges_after_two_rounds(tmp_path):
    cfg = _make_config(tmp_path)
    inp = _make_input(tmp_path)
    pipeline = Pipeline(cfg, MockModelClient(), FakeVerifier(cfg, rounds_to_pass=2), verbose=False)

    result = pipeline.run(inp)

    assert result.commit_passed is True
    assert result.pushed is True
    assert result.rounds_used == 2
    # 第 2 轮的日志与基线都应落盘
    assert (cfg.output_dir / "git_commit_round2.log").exists()
    assert (cfg.output_dir / "post_hook_baseline_round2.h").exists()


def test_pipeline_stops_at_max_rounds(tmp_path):
    cfg = _make_config(tmp_path)
    # 把上限压到 2，但要 5 轮才过 -> 不应 push
    cfg.raw["retry"]["max_fix_rounds"] = 2
    inp = _make_input(tmp_path)
    pipeline = Pipeline(cfg, MockModelClient(), FakeVerifier(cfg, rounds_to_pass=5), verbose=False)

    result = pipeline.run(inp)

    assert result.pushed is False
    assert result.commit_passed is False
    assert result.rounds_used == 2


def test_pipeline_handles_bad_prefix_gracefully(tmp_path):
    cfg = _make_config(tmp_path)
    bad = tmp_path / "not_in_prefix" / "foo.h"
    bad.parent.mkdir(parents=True)
    bad.write_text("x", encoding="utf-8")
    pipeline = Pipeline(cfg, MockModelClient(), FakeVerifier(cfg), verbose=False)

    result = pipeline.run(bad)

    assert result.converted is False
    assert result.pushed is False
    assert "源前缀" in result.error or "ValueError" in result.error


def test_pipeline_uses_scripted_model(tmp_path):
    """注入精确脚本化响应：初稿一个、修复一个，验证依赖注入可控。"""
    cfg = _make_config(tmp_path)
    inp = _make_input(tmp_path)

    initial = '{"file_type":"os_h","rewritten_code":"#ifndef G\\n#define G\\n#endif // G\\n","notes":"init"}'
    fixed = '{"rewritten_code":"#ifndef G2\\n#define G2\\n#endif // G2\\n","notes":"fixed"}'
    model = MockModelClient(responses=[initial, fixed])

    pipeline = Pipeline(cfg, model, FakeVerifier(cfg, rounds_to_pass=1), verbose=False)
    result = pipeline.run(inp)

    assert result.commit_passed is True
    assert result.rounds_used == 1
    # 初稿 + 1 轮修复 = 2 次模型调用
    assert len(model.calls) == 2
