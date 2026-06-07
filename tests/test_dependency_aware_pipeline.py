"""Dependency-aware header migration orchestration tests."""

from __future__ import annotations

import json
from pathlib import Path

from core.config import Config
from core.dep_graph import scan_dependency_graph
from core.inventory import scan_header_inventory
from core.migration_status import build_migration_status_report
from core.model_client import MockModelClient
from core.pipeline import Pipeline
from core.test_index import scan_test_index


def _make_config(tmp_path) -> Config:
    project = tmp_path / "project"
    (project / "skills").mkdir(parents=True)
    (project / "skills" / "rewrite_initial.md").write_text("initial prompt", encoding="utf-8")
    (project / "skills" / "rewrite_fix_from_log_and_test.md").write_text("fix prompt", encoding="utf-8")
    examples = project / "examples" / "headers"
    examples.mkdir(parents=True)
    for name in ("max.cccl.h", "max.accl.h", "os.cccl.h", "os.accl.h"):
        (examples / name).write_text(f"// {name}\n", encoding="utf-8")
    return Config.load(
        None,
        project_root=project,
        overrides={
            "model": {"provider": "mock"},
            "paths": {"accl_repo": str(tmp_path / "accl")},
        },
    )


def _seed_cccl_abc(tmp_path) -> Path:
    cccl = tmp_path / "cccl"
    include_root = cccl / "libcudacxx" / "include" / "cuda" / "std" / "__fixture"
    test_root = cccl / "libcudacxx" / "test" / "libcudacxx" / "std"
    include_root.mkdir(parents=True)
    test_root.mkdir(parents=True)
    (include_root / "a.h").write_text(
        "#include <cuda/std/__fixture/b.h>\nint a();\n",
        encoding="utf-8",
    )
    (include_root / "b.h").write_text(
        "#include <cuda/std/__fixture/c.h>\nint b();\n",
        encoding="utf-8",
    )
    (include_root / "c.h").write_text("int c();\n", encoding="utf-8")
    return cccl


def _seed_cccl_support_boundary(tmp_path) -> Path:
    cccl = tmp_path / "cccl"
    include_root = cccl / "libcudacxx" / "include" / "cuda" / "std"
    test_root = cccl / "libcudacxx" / "test" / "libcudacxx" / "std"
    (include_root / "__fixture").mkdir(parents=True)
    (include_root / "__internal").mkdir(parents=True)
    (include_root / "detail").mkdir(parents=True)
    test_root.mkdir(parents=True)
    (include_root / "__fixture" / "a.h").write_text(
        "\n".join(
            [
                "#include <cuda/std/__fixture/b.h>",
                "#include <cuda/std/__internal/support.h>",
                "#include <cuda/std/detail/__config>",
                "int a();",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (include_root / "__fixture" / "b.h").write_text("int b();\n", encoding="utf-8")
    (include_root / "__internal" / "support.h").write_text("int support();\n", encoding="utf-8")
    (include_root / "detail" / "__config").write_text("// upstream config\n", encoding="utf-8")
    return cccl


def _write_safe_target_and_ledger(tmp_path, cfg: Config) -> Path:
    target_file = (
        Path(cfg.target_repo)
        / "libascendcxx"
        / "include"
        / "ascend"
        / "std"
        / "__fixture"
        / "c.h"
    )
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text("// validated c\n", encoding="utf-8")
    ledger = tmp_path / "migration_ledger.md"
    ledger.write_text(
        "\n".join(
            [
                "| Source area | Item | Status | Notes |",
                "| --- | --- | --- | --- |",
                "| `__fixture` | `c.h` | host_passed | fixture dependency already safe |",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return ledger


def _write_bootstrap_config(cfg: Config) -> None:
    target_file = Path(cfg.target_repo) / "libascendcxx/include/ascend/std/__config"
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text("// hand-authored config\n", encoding="utf-8")


def _reports(cccl: Path, cfg: Config, ledger_path: Path | None = None):
    inventory = scan_header_inventory(cccl)
    test_index = scan_test_index(cccl)
    dep_graph = scan_dependency_graph(cccl)
    status = build_migration_status_report(
        inventory=inventory,
        test_index=test_index,
        dep_graph=dep_graph,
        target_repo=cfg.target_repo,
        ledger_path=ledger_path,
        target_repo_prefix=cfg.target_repo_prefix,
        segment_substitutions=cfg.segment_substitutions,
    )
    return inventory, test_index, dep_graph, status


def _context_entries(model: MockModelClient) -> list[str]:
    entries: list[str] = []
    decoder = json.JSONDecoder()
    marker = "【Node 11 bounded migration context pack】"
    for call in model.calls:
        text = call["user_content"]
        assert marker in text
        payload = text.split(marker, 1)[1].lstrip()
        pack, _ = decoder.raw_decode(payload)
        entries.append(pack["entry_header"])
    return entries


def test_dependency_aware_convert_rewrites_leaf_first_order(tmp_path):
    cfg = _make_config(tmp_path)
    cccl = _seed_cccl_abc(tmp_path)
    inventory, test_index, dep_graph, status = _reports(cccl, cfg)
    model = MockModelClient()
    pipeline = Pipeline(cfg, model, verifier=None, verbose=False)

    result = pipeline.convert_dependency_closure(
        entry_header="__fixture/a.h",
        inventory=inventory,
        test_index=test_index,
        dep_graph=dep_graph,
        status_report=status,
    )

    assert result.complete is True
    assert result.ordered_headers == ["__fixture/c.h", "__fixture/b.h", "__fixture/a.h"]
    assert result.rewritten_headers == ["__fixture/c.h", "__fixture/b.h", "__fixture/a.h"]
    assert result.skipped_headers == []
    assert _context_entries(model) == ["__fixture/c.h", "__fixture/b.h", "__fixture/a.h"]
    assert (
        Path(cfg.target_repo)
        / "libascendcxx/include/ascend/std/__fixture/a.h"
    ).exists()


def test_dependency_aware_convert_skips_safe_existing_dependencies(tmp_path):
    cfg = _make_config(tmp_path)
    cccl = _seed_cccl_abc(tmp_path)
    ledger = _write_safe_target_and_ledger(tmp_path, cfg)
    inventory, test_index, dep_graph, status = _reports(cccl, cfg, ledger)
    model = MockModelClient()
    pipeline = Pipeline(cfg, model, verifier=None, verbose=False)

    result = pipeline.convert_dependency_closure(
        entry_header="__fixture/a.h",
        inventory=inventory,
        test_index=test_index,
        dep_graph=dep_graph,
        status_report=status,
    )

    assert result.complete is True
    assert result.ordered_headers == ["__fixture/c.h", "__fixture/b.h", "__fixture/a.h"]
    assert result.skipped_headers == ["__fixture/c.h"]
    assert result.rewritten_headers == ["__fixture/b.h", "__fixture/a.h"]
    assert [item.action for item in result.items] == ["skipped", "rewritten", "rewritten"]
    assert _context_entries(model) == ["__fixture/b.h", "__fixture/a.h"]


def test_dependency_aware_plan_only_does_not_call_model_or_write_targets(tmp_path):
    cfg = _make_config(tmp_path)
    cccl = _seed_cccl_abc(tmp_path)
    ledger = _write_safe_target_and_ledger(tmp_path, cfg)
    inventory, test_index, dep_graph, status = _reports(cccl, cfg, ledger)
    model = MockModelClient(responses=[])
    pipeline = Pipeline(cfg, model, verifier=None, verbose=False)

    result = pipeline.convert_dependency_closure(
        entry_header="__fixture/a.h",
        inventory=inventory,
        test_index=test_index,
        dep_graph=dep_graph,
        status_report=status,
        plan_only=True,
    )

    assert result.complete is True
    assert result.ordered_headers == ["__fixture/c.h", "__fixture/b.h", "__fixture/a.h"]
    assert [item.action for item in result.items] == [
        "would_skip",
        "would_rewrite",
        "would_rewrite",
    ]
    assert model.calls == []
    assert not (
        Path(cfg.target_repo)
        / "libascendcxx/include/ascend/std/__fixture/a.h"
    ).exists()


def test_dependency_aware_plan_defers_support_surfaces(tmp_path):
    cfg = _make_config(tmp_path)
    _write_bootstrap_config(cfg)
    cccl = _seed_cccl_support_boundary(tmp_path)
    inventory, test_index, dep_graph, status = _reports(cccl, cfg)
    model = MockModelClient(responses=[])
    pipeline = Pipeline(cfg, model, verifier=None, verbose=False)

    result = pipeline.convert_dependency_closure(
        entry_header="__fixture/a.h",
        inventory=inventory,
        test_index=test_index,
        dep_graph=dep_graph,
        status_report=status,
        plan_only=True,
    )

    by_header = {item.source_header: item for item in result.items}
    assert by_header["__fixture/b.h"].action == "would_rewrite"
    assert by_header["__internal/support.h"].action == "would_skip"
    assert by_header["__internal/support.h"].reason == "deferred_upstream_support_only"
    assert by_header["detail/__config"].action == "would_skip"
    assert by_header["detail/__config"].reason == (
        "covered_by_bootstrap_manual:libascendcxx/include/ascend/std/__config"
    )
    assert by_header["__fixture/a.h"].action == "would_rewrite"
    assert model.calls == []
