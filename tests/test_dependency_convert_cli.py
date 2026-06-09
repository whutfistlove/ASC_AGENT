"""CLI tests for Node 12 dependency-aware conversion."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import main as cli


def _args(**overrides):
    base = {
        "cccl_repo": None,
        "entry_header": "__fixture/a.h",
        "mock": False,
        "no_write_target": False,
        "output": "dep_plan.json",
        "plan_only": False,
        "quiet": True,
        "real_ai": False,
        "settings": None,
        "show_model_io": False,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


def _seed_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    (project / "skills").mkdir(parents=True)
    (project / "examples" / "headers").mkdir(parents=True)
    return project


def _seed_cccl(tmp_path: Path) -> Path:
    cccl = tmp_path / "cccl"
    include_root = cccl / "libcudacxx/include/cuda/std/__fixture"
    test_root = cccl / "libcudacxx/test/libcudacxx/std"
    include_root.mkdir(parents=True)
    test_root.mkdir(parents=True)
    (include_root / "a.h").write_text("#include <cuda/std/__fixture/b.h>\n", encoding="utf-8")
    (include_root / "b.h").write_text("// leaf\n", encoding="utf-8")
    return cccl


def test_dependency_convert_requires_explicit_mode(capsys):
    code = cli.cmd_dependency_convert(_args())

    captured = capsys.readouterr()
    assert code == 2
    assert "choose --plan-only, --mock, or --real-ai explicitly" in captured.err


def test_dependency_convert_rejects_mock_and_real_ai(capsys):
    code = cli.cmd_dependency_convert(_args(mock=True, real_ai=True))

    captured = capsys.readouterr()
    assert code == 2
    assert "--mock and --real-ai are mutually exclusive" in captured.err


def test_dependency_convert_plan_only_writes_report_without_model(tmp_path, monkeypatch):
    project = _seed_project(tmp_path)
    cccl = _seed_cccl(tmp_path)
    monkeypatch.setattr(cli, "PROJECT_ROOT", project)
    monkeypatch.setattr(cli, "DEFAULT_SETTINGS", project / "config" / "settings.yaml")

    code = cli.cmd_dependency_convert(
        _args(
            cccl_repo=str(cccl),
            plan_only=True,
            output="fixture_dependency_plan.json",
        )
    )

    report_path = project / "outputs" / "fixture_dependency_plan.json"
    assert code == 0
    assert report_path.exists()
    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert data["complete"] is True
    assert data["ordered_headers"] == ["__fixture/b.h", "__fixture/a.h"]
    assert [item["action"] for item in data["items"]] == ["would_rewrite", "would_rewrite"]
