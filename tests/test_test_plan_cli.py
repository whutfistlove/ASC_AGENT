"""CLI coverage for Node 13 upstream test migration planning."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

# 命令实现已迁到 cli.commands；对该模块打桩/调用，使补丁命中真实查找命名空间。
from cli import commands as cli


def _args(**overrides):
    base = {
        "cccl_repo": None,
        "entry_header": "__algorithm/max.h",
        "max_selected_tests": 4,
        "output": "fixture_test_plan.json",
        "scaffold_inexpressible": [],
        "settings": None,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


def _migrate_args(**overrides):
    base = {
        "cccl_repo": None,
        "entry_header": "__algorithm/max.h",
        "mock": True,
        "output": "fixture_test_migration_artifacts.json",
        "quiet": True,
        "real_ai": False,
        "scaffold_inexpressible": [],
        "settings": None,
        "show_model_io": False,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


def _seed_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    (project / "docs").mkdir(parents=True)
    (project / "repos" / "accl").mkdir(parents=True)
    (project / "skills").mkdir(parents=True)
    (project / "skills" / "migrate_tests.md").write_text("return JSON\n", encoding="utf-8")
    return project


def _seed_cccl(tmp_path: Path) -> Path:
    cccl = tmp_path / "cccl"
    include_root = cccl / "libcudacxx" / "include" / "cuda" / "std"
    test_root = cccl / "libcudacxx" / "test" / "libcudacxx" / "std" / "algorithms"
    (include_root / "__algorithm").mkdir(parents=True)
    (include_root / "__utility").mkdir(parents=True)
    test_root.mkdir(parents=True)

    (include_root / "__algorithm" / "max.h").write_text("// max\n", encoding="utf-8")
    (include_root / "__utility" / "move.h").write_text("// move\n", encoding="utf-8")
    (test_root / "max.pass.cpp").write_text(
        "#include <cuda/std/__algorithm/max.h>\nint selected = 1;\n",
        encoding="utf-8",
    )
    (test_root / "max_comp.pass.cpp").write_text(
        "#include <cuda/std/__algorithm/max.h>\n#include <cuda/std/__utility/move.h>\nint blocked = 1;\n",
        encoding="utf-8",
    )
    (test_root / "max.verify.cpp").write_text(
        "#include <cuda/std/__algorithm/max.h>\nstatic_assert(true);\n",
        encoding="utf-8",
    )
    (test_root / "max.fail.cpp").write_text(
        "#include <cuda/std/__algorithm/max.h>\n#error expected failure\n",
        encoding="utf-8",
    )
    return cccl


def test_test_plan_cli_writes_selected_and_deferred_report(tmp_path, monkeypatch, capsys):
    project = _seed_project(tmp_path)
    cccl = _seed_cccl(tmp_path)
    monkeypatch.setattr(cli, "PROJECT_ROOT", project)
    monkeypatch.setattr(cli, "DEFAULT_SETTINGS", project / "config" / "settings.yaml")

    code = cli.cmd_test_plan(
        _args(
            cccl_repo=str(cccl),
            scaffold_inexpressible=["algorithms/max.pass.cpp"],
        )
    )

    captured = capsys.readouterr()
    report_path = project / "outputs" / "fixture_test_plan.json"
    assert code == 0
    assert "Node 13 upstream test migration plan" in captured.out
    assert report_path.exists()
    data = json.loads(report_path.read_text(encoding="utf-8"))

    assert data["entry_header"] == "__algorithm/max.h"
    assert data["summary"]["selected_count"] == 0
    deferred = {item["relative_path"]: item["reason"] for item in data["deferred_tests"]}
    assert deferred["algorithms/max.pass.cpp"] == "scaffold-inexpressible"
    assert deferred["algorithms/max_comp.pass.cpp"] == "dependency-blocked:__utility/move.h:pending"
    assert deferred["algorithms/max.verify.cpp"] == "verify-deferred"
    assert deferred["algorithms/max.fail.cpp"] == "compile-fail"


def test_test_migrate_requires_explicit_mode(capsys):
    code = cli.cmd_test_migrate(_migrate_args(mock=False, real_ai=False))

    captured = capsys.readouterr()
    assert code == 2
    assert "choose --mock or --real-ai explicitly" in captured.err


def test_test_migrate_mock_writes_artifact_report(tmp_path, monkeypatch, capsys):
    project = _seed_project(tmp_path)
    cccl = _seed_cccl(tmp_path)
    target = project / "repos/accl/asc-stl/include/asc/std/__algorithm/max.h"
    target.parent.mkdir(parents=True)
    target.write_text("// accl max\n", encoding="utf-8")
    monkeypatch.setattr(cli, "PROJECT_ROOT", project)
    monkeypatch.setattr(cli, "DEFAULT_SETTINGS", project / "config" / "settings.yaml")

    code = cli.cmd_test_migrate(_migrate_args(cccl_repo=str(cccl)))

    captured = capsys.readouterr()
    report_path = project / "outputs" / "fixture_test_migration_artifacts.json"
    assert code == 0
    assert "Node 13 AI test migration artifacts" in captured.out
    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert data["algo_name"] == "max"
    assert data["kernel_spec"]["dtype"] == "float"
    assert data["upstream_test_plan"]["summary"]["selected_count"] == 1
    deferred = {item["relative_path"]: item["reason"] for item in data["upstream_test_plan"]["deferred_tests"]}
    assert deferred["algorithms/max_comp.pass.cpp"] == "dependency-blocked:__utility/move.h:pending"
    assert deferred["algorithms/max.verify.cpp"] == "verify-deferred"
