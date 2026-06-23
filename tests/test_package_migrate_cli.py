"""CLI tests for the package-migrate driver."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

# 命令实现在 cli.commands；对该模块打桩使补丁命中真实查找命名空间。
from cli import commands as main


def _plan_dict(approved: bool = False, completed: list[str] | None = None) -> dict:
    def header(name: str) -> dict:
        return {
            "source_header": name,
            "target_relpath": f"asc-stl/include/asc/std/{name}",
            "include": f"cuda/std/{name}",
            "module": "__foo",
            "complexity_label": "easy",
            "complexity_score": 1,
            "direct_dependency_count": 0,
            "dependency_closure_size": 0,
            "true_missing_dependency_count": 0,
            "mapped_test_count": 0,
            "in_cycle": False,
            "status": "pending",
            "migrated": False,
        }

    return {
        "schema_version": 1,
        "approved": approved,
        "generated_at": "2026-06-23T00:00:00Z",
        "cccl_repo": "/tmp/cccl",
        "header_root": "/tmp/cccl/libcudacxx/include/cuda/std",
        "target_repo": "/tmp/accl",
        "manual_marks": [],
        "namespace": "cuda/std",
        "summary": {"total_headers": 2, "completed": 0, "pending": 2, "deferred": 0, "blocked": 0,
                    "batch_count": 2, "cycle_count": 0},
        "batches": [
            {"name": "batch-1", "wave": 1, "contains_cycle": False, "header_count": 1, "headers": [header("__foo/b.h")]},
            {"name": "batch-2", "wave": 2, "contains_cycle": False, "header_count": 1, "headers": [header("__foo/a.h")]},
        ],
        "completed_headers": [{"source_header": h, "target_relpath": "", "status": "full_passed", "evidence": "validated"}
                              for h in (completed or [])],
        "deferred_headers": [],
        "blocked_headers": [],
    }


def _args(plan_path: Path, **overrides) -> argparse.Namespace:
    base = dict(
        settings=None,
        plan=str(plan_path),
        batch="next",
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
    )
    base.update(overrides)
    return argparse.Namespace(**base)


def _write_plan(tmp_path: Path, **kwargs) -> Path:
    path = tmp_path / "package_migration_plan.json"
    path.write_text(json.dumps(_plan_dict(**kwargs)), encoding="utf-8")
    return path


def test_package_migrate_requires_approval(tmp_path):
    path = _write_plan(tmp_path)
    assert main.cmd_package_migrate(_args(path, batch="all")) == 2


def test_package_migrate_dispatches_in_wave_order(tmp_path, monkeypatch):
    path = _write_plan(tmp_path)
    seen: list[str] = []
    monkeypatch.setattr(main, "cmd_dependency_convert", lambda args: seen.append(args.entry_header) or 0)

    code = main.cmd_package_migrate(_args(path, approve=True, batch="all"))

    assert code == 0
    assert seen == ["__foo/b.h", "__foo/a.h"]


def test_package_migrate_next_skips_completed_batches(tmp_path, monkeypatch):
    path = _write_plan(tmp_path, completed=["__foo/b.h"])
    seen: list[str] = []
    monkeypatch.setattr(main, "cmd_dependency_convert", lambda args: seen.append(args.entry_header) or 0)

    code = main.cmd_package_migrate(_args(path, approve=True, batch="next"))

    assert code == 0
    assert seen == ["__foo/a.h"]  # batch-1 already complete, advance to batch-2


def test_package_migrate_next_nothing_left_is_success(tmp_path, monkeypatch):
    path = _write_plan(tmp_path, completed=["__foo/b.h", "__foo/a.h"])
    monkeypatch.setattr(main, "cmd_dependency_convert", lambda args: 0)

    assert main.cmd_package_migrate(_args(path, approve=True, batch="next")) == 0


def test_package_migrate_refreshes_ledger_after_run(tmp_path, monkeypatch):
    path = _write_plan(tmp_path)
    monkeypatch.setattr(main, "cmd_dependency_convert", lambda args: 0)
    refreshed = _plan_dict(approved=False, completed=["__foo/b.h"])

    captured: dict = {}

    def fake_build(config, cccl_repo, marks):
        captured["marks"] = marks
        return refreshed

    monkeypatch.setattr(main, "_build_package_plan", fake_build)

    # real_ai + not plan_only triggers the post-run ledger refresh.
    code = main.cmd_package_migrate(
        _args(path, approve=True, batch="batch-1", plan_only=False, real_ai=True)
    )

    assert code == 0
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["approved"] is True  # approval preserved across refresh
    assert [e["source_header"] for e in written["completed_headers"]] == ["__foo/b.h"]


def test_package_migrate_requires_mode_when_not_plan_only(tmp_path):
    path = _write_plan(tmp_path, approved=True)
    # not plan_only and neither mock nor real_ai -> usage error.
    assert main.cmd_package_migrate(_args(path, plan_only=False)) == 2
