"""Folder-level migration planning tests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

# 命令实现已迁到 cli.commands；测试针对该模块打桩/调用，使补丁命中真实查找命名空间。
from cli import commands as main
from core.analysis.dep_graph import scan_dependency_graph
from core.analysis.inventory import scan_header_inventory
from core.analysis.migration_status import build_migration_status_report
from core.analysis.test_index import scan_test_index
from core.common.config import Config
from core.planning.folder_planner import (
    FolderPlanOptions,
    build_folder_plan_payload,
    plan_to_markdown,
    write_folder_plan,
)


def _seed_repo(tmp_path: Path) -> Path:
    cccl = tmp_path / "cccl"
    header_root = cccl / "libcudacxx" / "include" / "cuda" / "std" / "__foo"
    test_root = cccl / "libcudacxx" / "test" / "libcudacxx" / "std" / "foo"
    header_root.mkdir(parents=True)
    test_root.mkdir(parents=True)
    (header_root / "b.h").write_text("template <class T> T b(T x){ return x; }\n", encoding="utf-8")
    (header_root / "a.h").write_text(
        '#include <cuda/std/__foo/b.h>\n'
        "template <class T> T a(T x){ return b(x); }\n",
        encoding="utf-8",
    )
    (test_root / "a.pass.cpp").write_text('#include <cuda/std/__foo/a.h>\n', encoding="utf-8")
    (test_root / "b.pass.cpp").write_text('#include <cuda/std/__foo/b.h>\n', encoding="utf-8")
    return cccl


def _seed_external_dependency_repo(tmp_path: Path) -> tuple[Path, Path, Path]:
    cccl = tmp_path / "cccl"
    include_root = cccl / "libcudacxx" / "include" / "cuda" / "std"
    test_root = cccl / "libcudacxx" / "test" / "libcudacxx" / "std"
    pkg = include_root / "__pkg"
    other = include_root / "__other"
    pkg.mkdir(parents=True)
    other.mkdir(parents=True)
    test_root.mkdir(parents=True)
    (pkg / "leaf.h").write_text("// leaf\n", encoding="utf-8")
    (pkg / "safe_external.h").write_text(
        "#include <cuda/std/__other/safe.h>\n",
        encoding="utf-8",
    )
    (pkg / "missing_external.h").write_text(
        "#include <cuda/std/__other/missing.h>\n",
        encoding="utf-8",
    )
    (pkg / "unverified_external.h").write_text(
        "#include <cuda/std/__other/unverified.h>\n",
        encoding="utf-8",
    )
    (pkg / "broken_external.h").write_text(
        "#include <cuda/std/__other/broken.h>\n",
        encoding="utf-8",
    )
    for name in ["safe.h", "missing.h", "unverified.h", "broken.h"]:
        (other / name).write_text(f"// {name}\n", encoding="utf-8")

    target = tmp_path / "accl"
    target_root = target / "asc-stl" / "include" / "asc" / "std" / "__other"
    target_root.mkdir(parents=True)
    (target_root / "safe.h").write_text("// safe\n", encoding="utf-8")
    (target_root / "unverified.h").write_text("// unverified\n", encoding="utf-8")
    (target_root / "broken.h").write_text(
        '#include "asc/std/__other/not_migrated.h"\n',
        encoding="utf-8",
    )

    ledger = tmp_path / "migration_ledger.md"
    ledger.write_text(
        "\n".join(
            [
                "| Source area | Item | Status | Notes |",
                "| --- | --- | --- | --- |",
                "| `__other` | `safe.h` | host_passed | checked |",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return cccl, target, ledger


def _config(tmp_path: Path) -> Config:
    return Config.load(
        None,
        project_root=tmp_path,
        overrides={"paths": {"accl_repo": str(tmp_path / "accl"), "output_dir": str(tmp_path / "outputs")}},
    )


def test_folder_plan_recommends_leaf_dependency_first(tmp_path):
    cccl = _seed_repo(tmp_path)
    cfg = _config(tmp_path)
    inventory = scan_header_inventory(cccl)
    test_index = scan_test_index(cccl)
    dep_graph = scan_dependency_graph(cccl)
    status = build_migration_status_report(
        inventory=inventory,
        test_index=test_index,
        dep_graph=dep_graph,
        target_repo=cfg.target_repo,
        target_repo_prefix=cfg.target_repo_prefix,
        segment_substitutions=cfg.segment_substitutions,
        policy=cfg.migration_policy,
    )

    plan = build_folder_plan_payload(
        config=cfg,
        source_dir="std/__foo",
        inventory=inventory,
        test_index=test_index,
        dep_graph=dep_graph,
        status_report=status,
        options=FolderPlanOptions(first_batch_size=1),
    )

    assert plan["scope_relpath"] == "__foo"
    assert plan["summary"]["header_count"] == 2
    assert plan["recommended_first_batch"][0]["source_header"] == "__foo/b.h"
    assert plan["followup_batches"][0]["headers"] == ["__foo/a.h"]
    a = next(item for item in plan["headers"] if item["source_header"] == "__foo/a.h")
    assert a["direct_dependencies"] == ["__foo/b.h"]
    assert a["in_scope_dependency_count"] == 1


def test_folder_plan_classifies_external_dependency_decisions(tmp_path):
    cccl, target, ledger = _seed_external_dependency_repo(tmp_path)
    cfg = Config.load(
        None,
        project_root=tmp_path,
        overrides={"paths": {"accl_repo": str(target), "output_dir": str(tmp_path / "outputs")}},
    )
    inventory = scan_header_inventory(cccl)
    test_index = scan_test_index(cccl)
    dep_graph = scan_dependency_graph(cccl)
    status = build_migration_status_report(
        inventory=inventory,
        test_index=test_index,
        dep_graph=dep_graph,
        target_repo=cfg.target_repo,
        ledger_path=ledger,
        target_repo_prefix=cfg.target_repo_prefix,
        segment_substitutions=cfg.segment_substitutions,
        policy=cfg.migration_policy,
    )

    plan = build_folder_plan_payload(
        config=cfg,
        source_dir="std/__pkg",
        inventory=inventory,
        test_index=test_index,
        dep_graph=dep_graph,
        status_report=status,
        options=FolderPlanOptions(first_batch_size=10),
    )
    by_header = {item["source_header"]: item for item in plan["headers"]}

    leaf = by_header["__pkg/leaf.h"]
    assert leaf["dependency_closure_size"] == 0
    assert [item["source_header"] for item in plan["independent_leaf_candidates"]] == ["__pkg/leaf.h"]

    safe = by_header["__pkg/safe_external.h"]
    assert safe["external_dependency_approval_required"] is False
    assert [dep["dependency"] for dep in safe["external_satisfied_dependencies"]] == ["__other/safe.h"]
    assert "external_dependencies_verified=1" in safe["planning_reasons"]

    missing = by_header["__pkg/missing_external.h"]
    assert missing["external_dependency_approval_required"] is True
    assert [dep["dependency"] for dep in missing["external_missing_dependencies"]] == ["__other/missing.h"]

    unverified = by_header["__pkg/unverified_external.h"]
    assert unverified["external_dependency_approval_required"] is True
    assert [dep["dependency"] for dep in unverified["external_unverified_dependencies"]] == ["__other/unverified.h"]

    broken = by_header["__pkg/broken_external.h"]
    assert broken["external_dependency_approval_required"] is True
    assert [dep["dependency"] for dep in broken["external_broken_dependencies"]] == ["__other/broken.h"]

    recommended = [item["source_header"] for item in plan["recommended_first_batch"]]
    assert "__pkg/missing_external.h" not in recommended
    assert "__pkg/unverified_external.h" not in recommended
    assert "__pkg/broken_external.h" not in recommended
    assert plan["summary"]["external_dependency_decision_count"] == 3

    markdown = plan_to_markdown(plan, json_name="plan.json", details_json_name="plan_details.json")
    assert "detail_json: `outputs/plan_details.json`" in markdown
    assert "top_missing:" in markdown
    assert "`__other/missing.h` x1" in markdown

    json_path, md_path = write_folder_plan(plan, tmp_path / "outputs", json_name="plan.json", md_name="plan.md")
    details_path = tmp_path / "outputs" / "plan_details.json"
    slim = json.loads(json_path.read_text(encoding="utf-8"))
    details = json.loads(details_path.read_text(encoding="utf-8"))
    assert json_path.exists()
    assert md_path.exists()
    assert details_path.exists()
    assert "dependency_closure" not in slim["headers"][0]
    assert "dependency_closure" in details["headers"][0]


def test_folder_plan_rejects_empty_source_scope(tmp_path):
    cccl = _seed_repo(tmp_path)
    cfg = _config(tmp_path)
    inventory = scan_header_inventory(cccl)
    test_index = scan_test_index(cccl)
    dep_graph = scan_dependency_graph(cccl)
    status = build_migration_status_report(
        inventory=inventory,
        test_index=test_index,
        dep_graph=dep_graph,
        target_repo=cfg.target_repo,
        target_repo_prefix=cfg.target_repo_prefix,
        segment_substitutions=cfg.segment_substitutions,
        policy=cfg.migration_policy,
    )

    try:
        build_folder_plan_payload(
            config=cfg,
            source_dir="std/__missing",
            inventory=inventory,
            test_index=test_index,
            dep_graph=dep_graph,
            status_report=status,
        )
    except ValueError as exc:
        assert "no headers" in str(exc)
    else:
        raise AssertionError("expected empty folder scope to be rejected")


def _folder_migrate_args(plan_path: Path, **overrides) -> argparse.Namespace:
    base = dict(
        settings=None,
        plan=str(plan_path),
        batch="first",
        approve=False,
        cccl_repo=None,
        plan_only=True,
        mock=False,
        real_ai=False,
        no_write_target=False,
        limit=0,
        continue_on_error=False,
        quiet=True,
        show_model_io=False,
        with_tests=False,
        host_only=False,
        kernel_only=False,
        kernel_mode="run_test",
        prepare_tests_only=False,
        overwrite_tests=False,
        kernel_fast=False,
        kernel_timeout=0,
        kernel_print_samples=None,
        test_dry_run=False,
        test_feedback_to_model=False,
        test_feedback_skill="rewrite_fix_from_log_and_test.md",
        max_fix_rounds=0,
        continue_on_test_failure=False,
        defer_dependents_on_failure=False,
        verify_includes=False,
        verify_includes_strict=False,
        allow_external_dependencies=False,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


def test_folder_migrate_requires_approval(tmp_path):
    plan = {
        "schema_version": 1,
        "approved": False,
        "recommended_first_batch": [{"source_header": "__foo/b.h"}],
        "followup_batches": [],
        "headers": [{"source_header": "__foo/b.h"}],
    }
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")

    assert main.cmd_folder_migrate(_folder_migrate_args(path)) == 2


def test_folder_migrate_dispatches_selected_headers_after_approval(tmp_path, monkeypatch):
    plan = {
        "schema_version": 1,
        "approved": False,
        "recommended_first_batch": [{"source_header": "__foo/b.h"}],
        "followup_batches": [{"name": "followup-1", "headers": ["__foo/a.h"]}],
        "headers": [{"source_header": "__foo/b.h"}, {"source_header": "__foo/a.h"}],
    }
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    seen: list[str] = []

    def fake_dependency_convert(args):
        seen.append(args.entry_header)
        return 0

    monkeypatch.setattr(main, "cmd_dependency_convert", fake_dependency_convert)

    code = main.cmd_folder_migrate(_folder_migrate_args(path, approve=True, batch="all", mock=True, plan_only=False))

    assert code == 0
    assert seen == ["__foo/b.h", "__foo/a.h"]


def test_folder_migrate_requires_external_dependency_approval(tmp_path, monkeypatch, capsys):
    plan = {
        "schema_version": 1,
        "approved": False,
        "recommended_first_batch": [{"source_header": "__foo/a.h"}],
        "followup_batches": [],
        "headers": [
            {
                "source_header": "__foo/a.h",
                "external_dependency_approval_required": True,
                "external_missing_dependencies": [{"dependency": "__bar/b.h"}],
                "external_unverified_dependencies": [],
                "external_broken_dependencies": [],
            }
        ],
    }
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    monkeypatch.setattr(main, "cmd_dependency_convert", lambda args: 0)

    blocked = main.cmd_folder_migrate(
        _folder_migrate_args(path, approve=True, mock=True, plan_only=False)
    )
    allowed = main.cmd_folder_migrate(
        _folder_migrate_args(
            path,
            approve=True,
            mock=True,
            plan_only=False,
            allow_external_dependencies=True,
        )
    )

    captured = capsys.readouterr()
    assert blocked == 2
    assert "requires external dependency approval" in captured.err
    assert allowed == 0


def test_folder_migrate_uses_config_default_cccl_repo(tmp_path, monkeypatch):
    plan = {
        "schema_version": 1,
        "approved": False,
        "recommended_first_batch": [{"source_header": "__foo/b.h"}],
        "followup_batches": [],
        "headers": [{"source_header": "__foo/b.h"}],
    }
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    monkeypatch.setattr(main, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(main, "DEFAULT_SETTINGS", tmp_path / "config" / "settings.yaml")
    seen: list[str] = []

    def fake_dependency_convert(args):
        seen.append(args.cccl_repo)
        return 0

    monkeypatch.setattr(main, "cmd_dependency_convert", fake_dependency_convert)

    code = main.cmd_folder_migrate(_folder_migrate_args(path, approve=True))

    assert code == 0
    assert seen == [str((tmp_path / "repos" / "cccl").resolve())]
