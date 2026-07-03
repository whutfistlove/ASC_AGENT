"""Whole-package dependency-wave planning tests."""

from __future__ import annotations

import json
from pathlib import Path

from core.analysis.dep_graph import scan_dependency_graph
from core.analysis.inventory import scan_header_inventory
from core.analysis.migration_status import build_migration_status_report
from core.analysis.test_index import scan_test_index
from core.common.config import Config
from core.planning.package_planner import (
    build_package_plan_payload,
    headers_for_batch,
    load_package_plan,
    read_manual_marks,
    write_package_plan,
)


def _seed_repo(tmp_path: Path) -> Path:
    cccl = tmp_path / "cccl"
    std = cccl / "libcudacxx" / "include" / "cuda" / "std"
    foo = std / "__foo"
    cccl_support = std / "__cccl"
    test_root = cccl / "libcudacxx" / "test" / "libcudacxx" / "std"
    foo.mkdir(parents=True)
    cccl_support.mkdir(parents=True)
    test_root.mkdir(parents=True)

    (foo / "leaf.h").write_text("template <class T> T leaf(T x){ return x; }\n", encoding="utf-8")
    (foo / "mid.h").write_text(
        '#include <cuda/std/__foo/leaf.h>\ntemplate <class T> T mid(T x){ return leaf(x); }\n',
        encoding="utf-8",
    )
    (foo / "top.h").write_text(
        '#include <cuda/std/__foo/mid.h>\ntemplate <class T> T top(T x){ return mid(x); }\n',
        encoding="utf-8",
    )
    # A 2-node dependency cycle.
    (foo / "cyc_a.h").write_text('#include <cuda/std/__foo/cyc_b.h>\n', encoding="utf-8")
    (foo / "cyc_b.h").write_text('#include <cuda/std/__foo/cyc_a.h>\n', encoding="utf-8")
    # Deferred-by-policy upstream support header (`__cccl/` prefix).
    (cccl_support / "support.h").write_text("// upstream support\n", encoding="utf-8")
    return cccl


def _config(tmp_path: Path) -> Config:
    return Config.load(
        None,
        project_root=tmp_path,
        overrides={"paths": {"accl_repo": str(tmp_path / "accl"), "output_dir": str(tmp_path / "outputs")}},
    )


def _build(tmp_path: Path, cccl: Path, cfg: Config, *, manual_marks=None, ledger=None):
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
    return build_package_plan_payload(
        config=cfg,
        inventory=inventory,
        dep_graph=dep_graph,
        test_index=test_index,
        status_report=status,
        manual_marks=set(manual_marks or set()),
    )


def _batch_of(plan: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for batch in plan["batches"]:
        for item in batch["headers"]:
            out[item["source_header"]] = batch["name"]
    return out


def test_package_plan_orders_chain_into_dependency_waves(tmp_path):
    cccl = _seed_repo(tmp_path)
    cfg = _config(tmp_path)
    plan = _build(tmp_path, cccl, cfg)

    batch_of = _batch_of(plan)
    # Strict dependency waves: leaf first, each dependent strictly later.
    assert batch_of["__foo/leaf.h"] == "batch-1"
    assert batch_of["__foo/mid.h"] == "batch-2"
    assert batch_of["__foo/top.h"] == "batch-3"

    # Every dependency lands in an earlier (or same, for cycles) batch — no violations.
    dep_graph = scan_dependency_graph(cccl)
    dep_by = {e.header: e.dependencies for e in dep_graph.graph}
    available = {e["source_header"] for e in plan["completed_headers"]} | {
        e["source_header"] for e in plan["deferred_headers"]
    }
    wave_of = {item["source_header"]: b["wave"] for b in plan["batches"] for item in b["headers"]}
    for header, wave in wave_of.items():
        for dep in dep_by.get(header, []):
            if dep in available:
                continue
            assert wave_of[dep] <= wave, f"{header} (wave {wave}) precedes dep {dep}"


def test_package_plan_co_locates_cycles_in_one_batch(tmp_path):
    cccl = _seed_repo(tmp_path)
    cfg = _config(tmp_path)
    plan = _build(tmp_path, cccl, cfg)

    batch_of = _batch_of(plan)
    assert batch_of["__foo/cyc_a.h"] == batch_of["__foo/cyc_b.h"]
    cyc_batch = next(b for b in plan["batches"] if b["name"] == batch_of["__foo/cyc_a.h"])
    assert cyc_batch["contains_cycle"] is True
    by_header = {item["source_header"]: item for b in plan["batches"] for item in b["headers"]}
    assert by_header["__foo/cyc_a.h"]["in_cycle"] is True
    assert by_header["__foo/leaf.h"]["in_cycle"] is False
    assert plan["summary"]["cycle_count"] == 1


def test_package_plan_defers_policy_headers(tmp_path):
    cccl = _seed_repo(tmp_path)
    cfg = _config(tmp_path)
    plan = _build(tmp_path, cccl, cfg)

    deferred = {e["source_header"]: e for e in plan["deferred_headers"]}
    assert "__cccl/support.h" in deferred
    assert deferred["__cccl/support.h"]["classification"] == "deferred_upstream_support"
    assert "__cccl/support.h" not in _batch_of(plan)


def test_package_plan_completed_pulls_dependents_forward(tmp_path):
    cccl = _seed_repo(tmp_path)
    cfg = _config(tmp_path)
    plan = _build(tmp_path, cccl, cfg, manual_marks={"__foo/leaf.h"})

    batch_of = _batch_of(plan)
    assert "__foo/leaf.h" not in batch_of  # completed, dropped from waves
    completed = {e["source_header"]: e for e in plan["completed_headers"]}
    assert completed["__foo/leaf.h"]["evidence"] == "manual"
    # leaf done -> mid becomes a frontier leaf, top moves one wave earlier.
    assert batch_of["__foo/mid.h"] == "batch-1"
    assert batch_of["__foo/top.h"] == "batch-2"


def test_package_plan_completes_via_validated_ledger(tmp_path):
    cccl = _seed_repo(tmp_path)
    # ACCL target for leaf must exist for ledger evidence to count as migrated.
    target_leaf = tmp_path / "accl" / "asc-stl" / "include" / "asc" / "std" / "__foo" / "leaf.h"
    target_leaf.parent.mkdir(parents=True)
    target_leaf.write_text("// migrated leaf\n", encoding="utf-8")
    ledger = tmp_path / "migration_ledger.md"
    ledger.write_text(
        "| Source area | Item | Status | Notes |\n| --- | --- | --- | --- |\n"
        "| `__foo` | `leaf.h` | full_passed | done |\n",
        encoding="utf-8",
    )
    cfg = _config(tmp_path)
    plan = _build(tmp_path, cccl, cfg, ledger=ledger)

    batch_of = _batch_of(plan)
    completed = {e["source_header"]: e for e in plan["completed_headers"]}
    assert "__foo/leaf.h" in completed
    assert completed["__foo/leaf.h"]["evidence"] == "validated"
    assert "__foo/leaf.h" not in batch_of
    assert batch_of["__foo/mid.h"] == "batch-1"


def test_package_plan_marks_persist_through_write_and_reload(tmp_path):
    cccl = _seed_repo(tmp_path)
    cfg = _config(tmp_path)
    plan = _build(tmp_path, cccl, cfg, manual_marks={"__foo/leaf.h"})
    json_path, md_path = write_package_plan(plan, cfg.output_dir, json_name="pkg.json", md_name="pkg.md")

    assert json_path.exists() and md_path.exists()
    assert read_manual_marks(json_path) == {"__foo/leaf.h"}
    reloaded = load_package_plan(json_path)
    assert reloaded["manual_marks"] == ["__foo/leaf.h"]
    md = md_path.read_text(encoding="utf-8")
    assert "[x] `__foo/leaf.h`" in md
    assert "batch-1" in md


def test_headers_for_batch_selectors(tmp_path):
    cccl = _seed_repo(tmp_path)
    cfg = _config(tmp_path)
    plan = _build(tmp_path, cccl, cfg)

    assert "__foo/leaf.h" in headers_for_batch(plan, "batch-1", set())
    assert headers_for_batch(plan, "batch-2", set()) == ["__foo/mid.h"]
    # `next` skips fully-completed leading batches.
    completed_first = {item["source_header"] for item in plan["batches"][0]["headers"]}
    assert headers_for_batch(plan, "next", completed_first) == ["__foo/mid.h"]
    # explicit comma list keeps only known, uncompleted headers.
    assert headers_for_batch(plan, "__foo/top.h,__foo/unknown.h", set()) == ["__foo/top.h"]


def _seed_two_layer_repo(tmp_path: Path) -> Path:
    """A cuda/std header + a cuda extension header that depends on it (cross-layer)."""
    cccl = tmp_path / "cccl"
    cuda = cccl / "libcudacxx" / "include" / "cuda"
    std_foo = cuda / "std" / "__foo"
    std_cccl = cuda / "std" / "__cccl"
    ext = cuda / "__bar"
    test_root = cccl / "libcudacxx" / "test" / "libcudacxx" / "cuda"
    std_foo.mkdir(parents=True)
    std_cccl.mkdir(parents=True)
    ext.mkdir(parents=True)
    test_root.mkdir(parents=True)
    (std_foo / "base.h").write_text("template <class T> T base(T x){ return x; }\n", encoding="utf-8")
    (std_cccl / "support.h").write_text("// upstream support\n", encoding="utf-8")
    # Extension header reaches across into the cuda/std layer.
    (ext / "uses_std.h").write_text(
        '#include <cuda/std/__foo/base.h>\ntemplate <class T> T bar(T x){ return base(x); }\n',
        encoding="utf-8",
    )
    return cccl


def test_package_plan_orders_cross_layer_dependencies(tmp_path):
    """Whole-tree (cuda root) analysis must order cuda/std deps before cuda extension users."""
    cccl = _seed_two_layer_repo(tmp_path)
    # cuda-root mapping (cuda -> asc), like config/settings.cuda.yaml / --all-layers.
    cfg = Config.load(
        None,
        project_root=tmp_path,
        overrides={
            "paths": {"accl_repo": str(tmp_path / "accl"), "output_dir": str(tmp_path / "outputs")},
            "mapping": {
                "source_repo_prefix": "libcudacxx/include/cuda",
                "target_repo_prefix": "asc-stl/include/asc",
                "cccl_test_prefix": "libcudacxx/test/libcudacxx/cuda",
            },
        },
    )
    root = cfg.source_repo_prefix
    inventory = scan_header_inventory(cccl, include_root_rel=root)
    test_index = scan_test_index(cccl, include_root_rel=root, test_root_rel=cfg.cccl_test_prefix)
    dep_graph = scan_dependency_graph(cccl, include_root_rel=root)
    status = build_migration_status_report(
        inventory=inventory,
        test_index=test_index,
        dep_graph=dep_graph,
        target_repo=cfg.target_repo,
        target_repo_prefix=cfg.target_repo_prefix,
        segment_substitutions=cfg.segment_substitutions,
        policy=cfg.migration_policy,
    )
    plan = build_package_plan_payload(
        config=cfg,
        inventory=inventory,
        dep_graph=dep_graph,
        test_index=test_index,
        status_report=status,
    )

    batch_of = _batch_of(plan)
    # Both layers present; std dep migrated before the extension header that needs it.
    assert "std/__foo/base.h" in batch_of
    assert "__bar/uses_std.h" in batch_of
    assert batch_of["std/__foo/base.h"] == "batch-1"
    assert batch_of["__bar/uses_std.h"] == "batch-2"
    # std target maps to asc/std/..., extension maps to asc/... — both correct under one plan.
    by_header = {item["source_header"]: item for b in plan["batches"] for item in b["headers"]}
    assert by_header["std/__foo/base.h"]["target_relpath"] == "asc-stl/include/asc/std/__foo/base.h"
    assert by_header["__bar/uses_std.h"]["target_relpath"] == "asc-stl/include/asc/__bar/uses_std.h"
    # Layer-aware policy: cuda/std infra under the cuda root is still deferred (not waved).
    deferred = {e["source_header"] for e in plan["deferred_headers"]}
    assert "std/__cccl/support.h" in deferred
    assert "std/__cccl/support.h" not in batch_of


def test_write_package_plan_rejects_pathy_names(tmp_path):
    cccl = _seed_repo(tmp_path)
    cfg = _config(tmp_path)
    plan = _build(tmp_path, cccl, cfg)
    for bad in ("sub/dir.json", "/abs.json"):
        try:
            write_package_plan(plan, cfg.output_dir, json_name=bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected rejection of {bad!r}")
    # JSON is deterministic / sorted so re-marking diffs are reviewable.
    json_path, _ = write_package_plan(plan, cfg.output_dir, json_name="pkg.json", md_name="pkg.md")
    parsed = json.loads(json_path.read_text(encoding="utf-8"))
    assert parsed["schema_version"] == 1
