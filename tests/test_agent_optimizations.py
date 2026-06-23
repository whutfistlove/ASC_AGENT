"""新增能力的离线单测：

  * migration_state 状态回写 + 新鲜度（闭合 能测 → 能扩）
  * build_migration_status_report 消费 state 证据
  * verify_includes 自包含 include 门
  * 闭包「局部可用、整体延期」（defer_dependents_on_failure）与 include 门接入
  * 预处理感知 include 扫描（#if 0 死块 / 条件块）
  * MigrationPolicy 配置化覆盖
  * example_promote 实测状态门禁
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from core.analysis.dep_graph import scan_dependency_graph
from core.analysis.inventory import scan_cuda_std_includes, scan_header_inventory
from core.analysis.migration_state import (
    MigrationStateStore,
    classify_status,
    source_sha,
)
from core.analysis.migration_status import build_migration_status_report
from core.analysis.test_index import scan_test_index
from core.common.config import Config, MigrationPolicy, default_migration_policy
from core.llm.model_client import MockModelClient
from core.migration.pipeline import Pipeline, _transitive_dependents
from core.testing.verify_includes import (
    include_directive_for,
    parse_missing_includes,
    verify_header_self_contained,
)


# --------------------------------------------------------------------------- #
# 公共脚手架
# --------------------------------------------------------------------------- #
def _make_config(tmp_path) -> Config:
    project = tmp_path / "project"
    (project / "skills").mkdir(parents=True)
    (project / "skills" / "rewrite_initial.md").write_text("initial prompt", encoding="utf-8")
    examples = project / "examples" / "headers"
    examples.mkdir(parents=True)
    # 默认配置的 example_1/2 指向 max/os，两者都需存在（select_header_examples 会读取）。
    for name in ("max.cccl.h", "max.accl.h", "os.cccl.h", "os.accl.h"):
        (examples / name).write_text(f"// {name}\n", encoding="utf-8")
    return Config.load(
        None,
        project_root=project,
        overrides={
            "model": {"provider": "mock"},
            "paths": {
                "accl_repo": str(tmp_path / "accl"),
                "output_dir": str(tmp_path / "outputs"),
            },
        },
    )


def _seed_cccl_branch(tmp_path) -> Path:
    """分叉闭包：a 依赖 b 与 d；b 依赖 c（叶子）；d 独立。用于验证「只延期 c 的下游」。"""
    cccl = tmp_path / "cccl"
    root = cccl / "libcudacxx" / "include" / "cuda" / "std" / "__fixture"
    (cccl / "libcudacxx" / "test" / "libcudacxx" / "std").mkdir(parents=True)
    root.mkdir(parents=True)
    (root / "a.h").write_text(
        "#include <cuda/std/__fixture/b.h>\n#include <cuda/std/__fixture/d.h>\nint a();\n",
        encoding="utf-8",
    )
    (root / "b.h").write_text("#include <cuda/std/__fixture/c.h>\nint b();\n", encoding="utf-8")
    (root / "c.h").write_text("int c();\n", encoding="utf-8")
    (root / "d.h").write_text("int d();\n", encoding="utf-8")
    return cccl


def _reports(cccl: Path, cfg: Config, *, state_status_map=None):
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
        state_status_map=state_status_map,
    )
    return inventory, test_index, dep_graph, status


# --------------------------------------------------------------------------- #
# migration_state
# --------------------------------------------------------------------------- #
def test_classify_status():
    assert classify_status(host_passed=True, kernel_passed=True) == "full_passed"
    assert classify_status(host_passed=False, kernel_passed=True) == "kernel_passed"
    assert classify_status(host_passed=True, kernel_passed=False) == "host_passed"
    assert classify_status(host_passed=False, kernel_passed=False) == "generated"


def test_state_store_record_save_load_roundtrip(tmp_path):
    path = tmp_path / "migration_state.json"
    store = MigrationStateStore.load(path)
    store.record(
        source_header="__algorithm/min.h",
        target_relpath="asc-stl/include/asc/std/__algorithm/min.h",
        source_text="int min();\n",
        host_passed=True,
        kernel_passed=True,
    )
    store.save(path)

    reloaded = MigrationStateStore.load(path)
    entry = reloaded.headers["__algorithm/min.h"]
    assert entry.status == "full_passed"
    assert entry.source_sha == source_sha("int min();\n")
    assert entry.host_passed and entry.kernel_passed


def test_state_store_freshness_filters_changed_sources(tmp_path):
    header_root = tmp_path / "src"
    (header_root / "__algorithm").mkdir(parents=True)
    src = header_root / "__algorithm" / "min.h"
    src.write_text("int min();\n", encoding="utf-8")

    store = MigrationStateStore(path=tmp_path / "s.json")
    store.record(
        source_header="__algorithm/min.h",
        target_relpath="t/min.h",
        source_text=src.read_text(encoding="utf-8"),
        host_passed=True,
        kernel_passed=False,
    )
    # 源未变：作为已验证证据返回。
    assert store.fresh_status_map(header_root) == {"__algorithm/min.h": "host_passed"}

    # 源变了：不再算「已验证」（强制重迁）。
    src.write_text("int min(int);\n", encoding="utf-8")
    assert store.fresh_status_map(header_root) == {}

    # 未通过的记录从不进入证据集合。
    store.record(source_header="__algorithm/x.h", target_relpath="t/x.h",
                 source_text=None, host_passed=False, kernel_passed=False)
    assert "__algorithm/x.h" not in store.fresh_status_map(header_root)


def test_recorded_state_makes_closure_skip_validated_dependency(tmp_path):
    """端到端闭环证明：记录 c.h 验证通过 → 状态报告判其 full_passed → 闭包计划自动跳过它。

    这是本轮最关键的修复：没有任何手写 ledger，仅靠自动回写的 migration_state 就实现了
    「已验证、未变的依赖直接跳过」。"""
    cfg = _make_config(tmp_path)
    cccl = _seed_cccl_branch(tmp_path)
    inventory = scan_header_inventory(cccl)

    # c.h 的目标头已存在（跳过需 target_exists）。
    target = Path(cfg.target_repo) / "asc-stl/include/asc/std/__fixture/c.h"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("int c();\n", encoding="utf-8")

    # 用 c.h 的真实源内容记录一次通过 → fresh_status_map 据源哈希认其为已验证。
    store = MigrationStateStore(path=tmp_path / "migration_state.json")
    c_src = Path(inventory.header_root) / "__fixture" / "c.h"
    store.record(
        source_header="__fixture/c.h",
        target_relpath="asc-stl/include/asc/std/__fixture/c.h",
        source_text=c_src.read_text(encoding="utf-8"),
        host_passed=True,
        kernel_passed=True,
    )
    state_map = store.fresh_status_map(inventory.header_root)
    assert state_map == {"__fixture/c.h": "full_passed"}

    _, test_index, dep_graph, status = _reports(cccl, cfg, state_status_map=state_map)
    pipeline = Pipeline(cfg, MockModelClient(responses=[]), verifier=None, verbose=False)
    result = pipeline.convert_dependency_closure(
        entry_header="__fixture/a.h",
        inventory=inventory,
        test_index=test_index,
        dep_graph=dep_graph,
        status_report=status,
        plan_only=True,
    )

    by_header = {it.source_header: it for it in result.items}
    assert by_header["__fixture/c.h"].action == "would_skip"
    assert "__fixture/c.h" in result.skipped_headers
    assert by_header["__fixture/b.h"].action == "would_rewrite"  # 未验证的仍要迁


def test_status_report_consumes_state_evidence(tmp_path):
    cfg = _make_config(tmp_path)
    cccl = _seed_cccl_branch(tmp_path)
    # c.h 的目标头存在（status 需 target_exists 才会被判为已验证）。
    target = Path(cfg.target_repo) / "asc-stl/include/asc/std/__fixture/c.h"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("int c();\n", encoding="utf-8")

    _, _, _, status = _reports(cccl, cfg, state_status_map={"__fixture/c.h": "full_passed"})
    by_header = {h.source_header: h for h in status.headers}
    assert by_header["__fixture/c.h"].status == "full_passed"
    assert "validated_via_state_store" in by_header["__fixture/c.h"].notes


# --------------------------------------------------------------------------- #
# verify_includes
# --------------------------------------------------------------------------- #
def test_include_directive_for():
    assert include_directive_for("asc-stl/include/asc/std/__algorithm/min.h") == "asc/std/__algorithm/min.h"
    assert include_directive_for("asc/std/foo.h") == "asc/std/foo.h"  # 已是相对 include 根


def test_parse_missing_includes():
    diag = "x.cpp:1:10: fatal error: 'asc/std/__utility/pair.h' file not found\n"
    assert parse_missing_includes(diag) == ["asc/std/__utility/pair.h"]
    gcc = "x.cpp:1:10: fatal error: asc/std/__x/y.h: No such file or directory\n"
    assert parse_missing_includes(gcc) == ["asc/std/__x/y.h"]


@pytest.mark.skipif(not shutil.which("g++"), reason="requires g++")
def test_verify_header_self_contained_detects_missing_and_ok(tmp_path):
    inc = tmp_path / "asc-stl" / "include" / "asc" / "std" / "__fixture"
    inc.mkdir(parents=True)
    # 自包含、可编译的头。
    (inc / "leaf.h").write_text(
        "#ifndef LEAF_H\n#define LEAF_H\ninline int leaf() { return 0; }\n#endif\n",
        encoding="utf-8",
    )
    ok = verify_header_self_contained(
        target_repo=tmp_path, target_relpath="asc-stl/include/asc/std/__fixture/leaf.h"
    )
    assert ok.available and ok.ran and ok.ok and ok.missing_includes == []

    # 引用未迁移 sibling 的头：应抓到缺失 include。
    (inc / "dependent.h").write_text(
        '#ifndef DEP_H\n#define DEP_H\n#include "asc/std/__fixture/not_migrated.h"\n#endif\n',
        encoding="utf-8",
    )
    bad = verify_header_self_contained(
        target_repo=tmp_path, target_relpath="asc-stl/include/asc/std/__fixture/dependent.h"
    )
    assert bad.ran and not bad.ok
    assert "asc/std/__fixture/not_migrated.h" in bad.missing_includes


# --------------------------------------------------------------------------- #
# 闭包：局部可用、整体延期
# --------------------------------------------------------------------------- #
def test_transitive_dependents():
    dep_map = {"a": ["b", "d"], "b": ["c"], "c": [], "d": []}
    universe = {"a", "b", "c", "d"}
    assert _transitive_dependents("c", dep_map, universe) == {"a", "b"}
    assert _transitive_dependents("d", dep_map, universe) == {"a"}


def test_closure_defers_only_dependents_of_failed_leaf(tmp_path):
    cfg = _make_config(tmp_path)
    cccl = _seed_cccl_branch(tmp_path)
    inventory, test_index, dep_graph, status = _reports(cccl, cfg)
    pipeline = Pipeline(cfg, MockModelClient(), verifier=None, verbose=False)

    def on_rewritten(run_result):
        is_failure = run_result.target_relpath.endswith("__fixture/c.h")
        return is_failure, {"host_passed": not is_failure}

    result = pipeline.convert_dependency_closure(
        entry_header="__fixture/a.h",
        inventory=inventory,
        test_index=test_index,
        dep_graph=dep_graph,
        status_report=status,
        on_rewritten=on_rewritten,
        defer_dependents_on_failure=True,
    )

    # c 失败 → 只延期依赖它的 b、a；独立分支 d 照常迁移。整条闭包优雅收尾（无 error）。
    assert result.complete is True
    assert result.error == ""
    assert "__fixture/c.h" in result.rewritten_headers
    assert "__fixture/d.h" in result.rewritten_headers
    assert result.failed_test_headers == ["__fixture/c.h"]
    assert set(result.deferred_headers) == {"__fixture/b.h", "__fixture/a.h"}


@pytest.mark.skipif(not shutil.which("g++"), reason="requires g++")
def test_closure_include_gate_flags_unresolved(tmp_path):
    cfg = _make_config(tmp_path)
    cccl = _seed_cccl_branch(tmp_path)
    inventory, test_index, dep_graph, status = _reports(cccl, cfg)

    # 让模型为叶子 c.h 产出一个引用未迁移 sibling 的头（include 不自包含）。
    bad_header = (
        "#ifndef ASC_STL_INCLUDE_ASC_STD___FIXTURE_C_H_\n"
        "#define ASC_STL_INCLUDE_ASC_STD___FIXTURE_C_H_\n"
        '#include "asc/std/__fixture/ghost.h"\n'
        "#endif\n"
    )
    responses = [json.dumps({"file_type": "h", "rewritten_code": bad_header, "notes": "x"})]
    pipeline = Pipeline(cfg, MockModelClient(responses=responses), verifier=None, verbose=False)

    result = pipeline.convert_dependency_closure(
        entry_header="__fixture/c.h",  # 叶子，无依赖：闭包只此一个头
        inventory=inventory,
        test_index=test_index,
        dep_graph=dep_graph,
        status_report=status,
        verify_includes=True,
        verify_includes_strict=True,
    )

    item = next(it for it in result.items if it.source_header == "__fixture/c.h")
    assert item.include_check["ran"] and not item.include_check["ok"]
    assert "asc/std/__fixture/ghost.h" in item.include_check["missing_includes"]
    assert result.failed_test_headers == ["__fixture/c.h"]


# --------------------------------------------------------------------------- #
# 预处理感知 include 扫描
# --------------------------------------------------------------------------- #
def test_scan_includes_drops_if0_and_flags_conditional():
    text = (
        "#ifndef GUARD\n#define GUARD\n"
        "#include <cuda/std/__always.h>\n"
        "#if 0\n#include <cuda/std/__dead.h>\n#else\n#include <cuda/std/__live.h>\n#endif\n"
        "#ifdef ASC_HAS_X\n#include <cuda/std/__cond.h>\n#endif\n"
        "#endif\n"
    )
    scan = scan_cuda_std_includes(text)
    assert "cuda/std/__dead.h" in scan.dead
    assert "cuda/std/__dead.h" not in scan.active
    assert "cuda/std/__live.h" in scan.active            # #else of #if 0 is live
    assert "cuda/std/__always.h" in scan.active
    assert "cuda/std/__always.h" not in scan.conditional  # guard-only is not conditional
    assert "cuda/std/__cond.h" in scan.conditional        # inside #ifdef → conditional


# --------------------------------------------------------------------------- #
# MigrationPolicy 配置化
# --------------------------------------------------------------------------- #
def test_migration_policy_override(tmp_path):
    cfg = Config.load(
        None,
        project_root=tmp_path,
        overrides={"migration_policy": {"deferred_upstream_support_prefixes": ["__only/"]}},
    )
    policy = cfg.migration_policy
    assert policy.deferred_upstream_support_prefixes == ("__only/",)
    # 未覆盖项回退到内置默认。
    assert "__config" in policy.bootstrap_manual_coverage.values()
    assert default_migration_policy().deferred_upstream_support_prefixes[0] == "__cccl/"
