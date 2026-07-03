"""Machine-readable migration status reporting.

The report combines real CCCL inventory/test/dependency scans with the ACCL
target tree. Optional ledger parsing is used only as validation evidence; target
files must still exist before a header is considered migrated.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from core.analysis.dep_graph import HeaderDependencyGraphReport, scan_dependency_graph
from core.analysis.inventory import (
    HEADER_ROOT_REL,
    HeaderInventoryReport,
    namespace_for_root,
    scan_header_inventory,
)
from core.analysis.path_mapper import apply_segment_substitutions, normalize_path_str
from core.analysis.target_inventory import TargetHeaderInventoryReport, scan_target_header_inventory
from core.analysis.test_index import TEST_ROOT_REL, CCCLTestIndexReport, scan_test_index
from core.common.config import MigrationPolicy, default_migration_policy
from core.common.utils import save_text

DEFAULT_MIGRATION_STATUS_REPORT_NAME = "migration_status.json"

STATUS_VALUES: tuple[str, ...] = (
    "pending",
    "generated",
    "host_passed",
    "kernel_passed",
    "full_passed",
    "blocked_env",
    "blocked_design",
)
_STATUS_RANK = {status: idx for idx, status in enumerate(STATUS_VALUES)}
_LEDGER_STATUSES = set(STATUS_VALUES)
_TARGET_STD_PREFIX = "asc-stl/include/asc/std"
MISSING_DEPENDENCY_CLASSIFICATIONS: tuple[str, ...] = (
    "true_dependency_gap",
    "bootstrap_manual",
    "target_only_compatibility_wrapper",
    "public_aggregation_narrowed",
    "deferred_upstream_support_only",
)
# 迁移策略已收敛到 core.common.config.MigrationPolicy（单一事实源）；这里仅保留默认实例的便捷引用。
# 历史调用方仍可不传 policy，行为与之前完全一致。


@dataclass(frozen=True)
class LedgerStatusEntry:
    key: str
    status: str
    source: str

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "source": self.source,
            "status": self.status,
        }


@dataclass(frozen=True)
class HeaderMigrationStatusEntry:
    source_header: str
    include: str
    module: str
    shape: str
    target_relpath: str
    target_exists: bool
    status: str
    ledger_status: str | None
    host_test_exists: bool
    kernel_spec_exists: bool
    target_include_missing_dependencies: list[str]
    dependencies: list[str]
    missing_dependencies: list[str]
    mapped_tests: list[str]
    notes: list[str]

    def to_dict(self) -> dict:
        return {
            "dependencies": list(self.dependencies),
            "host_test_exists": self.host_test_exists,
            "include": self.include,
            "kernel_spec_exists": self.kernel_spec_exists,
            "ledger_status": self.ledger_status,
            "mapped_tests": list(self.mapped_tests),
            "missing_dependencies": list(self.missing_dependencies),
            "module": self.module,
            "notes": list(self.notes),
            "shape": self.shape,
            "source_header": self.source_header,
            "status": self.status,
            "target_include_missing_dependencies": list(self.target_include_missing_dependencies),
            "target_exists": self.target_exists,
            "target_relpath": self.target_relpath,
        }


@dataclass(frozen=True)
class TargetOnlyHeaderEntry:
    target_relpath: str
    status: str
    ledger_status: str | None
    host_test_exists: bool
    kernel_spec_exists: bool
    classification: str

    def to_dict(self) -> dict:
        return {
            "classification": self.classification,
            "host_test_exists": self.host_test_exists,
            "kernel_spec_exists": self.kernel_spec_exists,
            "ledger_status": self.ledger_status,
            "status": self.status,
            "target_relpath": self.target_relpath,
        }


@dataclass(frozen=True)
class MissingDependencyEntry:
    header: str
    dependency: str
    dependency_target_relpath: str
    classification: str
    reason: str

    def to_dict(self) -> dict:
        return {
            "classification": self.classification,
            "dependency": self.dependency,
            "dependency_target_relpath": self.dependency_target_relpath,
            "header": self.header,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class BatchCandidateEntry:
    source_header: str
    include: str
    module: str
    shape: str
    target_relpath: str
    status: str
    dependency_closure_size: int
    true_missing_dependency_count: int
    classified_missing_dependency_counts: dict[str, int]
    mapped_tests: list[str]
    test_kind_counts: dict[str, int]
    host_test_suitability: str
    kernel_test_suitability: str
    target_exists: bool
    host_test_exists: bool
    kernel_spec_exists: bool
    score: int
    rank_reasons: list[str]

    def to_dict(self) -> dict:
        return {
            "classified_missing_dependency_counts": dict(self.classified_missing_dependency_counts),
            "dependency_closure_size": self.dependency_closure_size,
            "host_test_exists": self.host_test_exists,
            "host_test_suitability": self.host_test_suitability,
            "include": self.include,
            "kernel_spec_exists": self.kernel_spec_exists,
            "kernel_test_suitability": self.kernel_test_suitability,
            "mapped_tests": list(self.mapped_tests),
            "module": self.module,
            "rank_reasons": list(self.rank_reasons),
            "score": self.score,
            "shape": self.shape,
            "source_header": self.source_header,
            "status": self.status,
            "target_exists": self.target_exists,
            "target_relpath": self.target_relpath,
            "test_kind_counts": dict(self.test_kind_counts),
            "true_missing_dependency_count": self.true_missing_dependency_count,
        }


@dataclass(frozen=True)
class MigrationStatusReport:
    cccl_repo: str
    header_root: str
    test_root: str
    target_repo: str
    headers: list[HeaderMigrationStatusEntry]
    target_only_headers: list[TargetOnlyHeaderEntry]
    missing_dependencies: list[MissingDependencyEntry]
    mapped_tests: list[dict]
    unmapped_tests: list[str]
    unmapped_headers: list[str]
    ledger_entries: list[LedgerStatusEntry]
    dep_graph_cycles: list[list[str]]
    batch_candidates: list[BatchCandidateEntry]
    target_headers: list[dict]

    def summary(self) -> dict:
        status_counts = {status: 0 for status in STATUS_VALUES}
        for entry in self.headers:
            status_counts[entry.status] += 1
        migrated_headers = [entry.source_header for entry in self.headers if entry.status != "pending"]
        classification_counts = {name: 0 for name in MISSING_DEPENDENCY_CLASSIFICATIONS}
        for entry in self.missing_dependencies:
            classification_counts[entry.classification] += 1
        return {
            "batch_candidate_count": len(self.batch_candidates),
            "dep_graph_cycle_count": len(self.dep_graph_cycles),
            "header_count": len(self.headers),
            "ledger_entry_count": len(self.ledger_entries),
            "mapped_header_count": len(self.mapped_tests),
            "migrated_header_count": len(migrated_headers),
            "missing_dependency_classification_counts": classification_counts,
            "missing_dependency_count": len(self.missing_dependencies),
            "status_counts": status_counts,
            "target_broken_header_count": sum(
                1 for entry in self.target_headers if entry.get("missing_include_dependencies")
            ),
            "target_header_count": len(self.target_headers),
            "target_missing_include_count": sum(
                len(entry.get("missing_include_dependencies") or []) for entry in self.target_headers
            ),
            "target_only_header_count": len(self.target_only_headers),
            "unmapped_header_count": len(self.unmapped_headers),
            "unmapped_test_count": len(self.unmapped_tests),
        }

    def to_dict(self) -> dict:
        migrated_headers = [entry.source_header for entry in self.headers if entry.status != "pending"]
        return {
            "batch_candidates": [entry.to_dict() for entry in self.batch_candidates],
            "cccl_repo": self.cccl_repo,
            "dep_graph_cycles": [list(cycle) for cycle in self.dep_graph_cycles],
            "header_root": self.header_root,
            "headers": [entry.to_dict() for entry in self.headers],
            "ledger_entries": [entry.to_dict() for entry in self.ledger_entries],
            "mapped_tests": list(self.mapped_tests),
            "migrated_headers": migrated_headers,
            "missing_dependencies": [entry.to_dict() for entry in self.missing_dependencies],
            "summary": self.summary(),
            "target_headers": list(self.target_headers),
            "target_only_headers": [entry.to_dict() for entry in self.target_only_headers],
            "target_repo": self.target_repo,
            "test_root": self.test_root,
            "unmapped_headers": list(self.unmapped_headers),
            "unmapped_tests": list(self.unmapped_tests),
        }


def _split_markdown_row(line: str) -> list[str] | None:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    cells = [cell.strip() for cell in stripped.strip("|").split("|")]
    if not cells or all(set(cell) <= {"-", " "} for cell in cells):
        return None
    return cells


def _strip_code(text: str) -> str:
    return text.strip().strip("`").strip()


def _code_spans(text: str) -> list[str]:
    return re.findall(r"`([^`]+)`", text)


def _ledger_source_keys(area: str, item: str) -> list[str]:
    area = _strip_code(area)
    item = item.strip()
    spans = [span for span in _code_spans(item) if span.endswith(".h") or "." not in span]
    raw_items = spans or [_strip_code(item)]
    keys: set[str] = set()
    for raw in raw_items:
        raw = raw.strip()
        if not raw:
            continue
        if raw.startswith("asc/std/"):
            keys.add(_TARGET_STD_PREFIX + "/" + raw[len("asc/std/"):])
            continue
        if raw.startswith(_TARGET_STD_PREFIX + "/"):
            keys.add(raw)
            continue
        if raw.startswith("__") or "/" in raw:
            if raw.startswith(area + "/"):
                keys.add(raw)
            else:
                keys.add(f"{area}/{raw}" if area.startswith("__") else raw)
        elif area.startswith("__"):
            keys.add(f"{area}/{raw}")
        else:
            keys.add(raw)
    return sorted(keys)


def parse_migration_ledger_statuses(ledger_path: str | Path) -> list[LedgerStatusEntry]:
    """Parse status rows from `docs/migration_ledger.md`.

    This intentionally extracts only compact row evidence. Free-form prose stays
    human-owned and is not rewritten by the status generator.
    """
    path = Path(ledger_path)
    if not path.exists():
        return []
    entries: list[LedgerStatusEntry] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        cells = _split_markdown_row(line)
        if not cells:
            continue
        if len(cells) >= 4 and cells[2] in _LEDGER_STATUSES:
            for key in _ledger_source_keys(cells[0], cells[1]):
                entries.append(LedgerStatusEntry(key=key, status=cells[2], source=str(path)))
        elif len(cells) >= 3 and cells[1] in _LEDGER_STATUSES and cells[0].startswith("`asc/std/"):
            key = _TARGET_STD_PREFIX + "/" + _strip_code(cells[0])[len("asc/std/"):]
            entries.append(LedgerStatusEntry(key=key, status=cells[1], source=str(path)))
    dedup: dict[str, LedgerStatusEntry] = {}
    for entry in entries:
        previous = dedup.get(entry.key)
        if previous is None or _STATUS_RANK[entry.status] >= _STATUS_RANK[previous.status]:
            dedup[entry.key] = entry
    return [dedup[key] for key in sorted(dedup)]


def policy_key(name: str) -> str:
    """Normalize a header/dependency key to its cuda/std-relative form for policy matching.

    Whole-tree (cuda root) scans key std headers as ``std/__cccl/...`` while the
    migration_policy prefixes/sets are expressed relative to the cuda/std namespace
    (``__cccl/...``). Stripping a single leading ``std/`` makes both layers match the
    same policy. No-op for single-layer scans (keys never start with ``std/``).
    """
    return name[len("std/"):] if name.startswith("std/") else name


def target_relpath_for_header(
    source_header: str,
    *,
    target_repo_prefix: str = _TARGET_STD_PREFIX,
    segment_substitutions: list[dict] | None = None,
) -> str:
    rel = apply_segment_substitutions(source_header, segment_substitutions)
    return normalize_path_str(target_repo_prefix).rstrip("/") + "/" + rel


def _target_header_relpath(path: Path, target_repo: Path) -> str:
    return path.relative_to(target_repo).as_posix()


def _target_header_paths(target_repo: Path, target_repo_prefix: str) -> list[Path]:
    root = target_repo / normalize_path_str(target_repo_prefix)
    if not root.is_dir():
        return []
    return sorted(path for path in root.rglob("*") if path.is_file())


def _algo_names_for_header(source_header: str) -> list[str]:
    stem = Path(source_header).stem
    names = {stem}
    if stem == "gcd_lcm":
        names.update({"gcd", "lcm"})
    return sorted(names)


def _host_test_exists(target_repo: Path, source_header: str) -> bool:
    host_root = target_repo / "asc-stl/test/asc-stl/asc/host"
    return any((host_root / f"{name}_tests.cpp").exists() for name in _algo_names_for_header(source_header))


def _kernel_spec_exists(target_repo: Path, source_header: str) -> bool:
    kernel_root = target_repo / "asc-stl/test/asc-stl/asc/kernel"
    return any((kernel_root / f"{name}_example" / "kernel_spec.json").exists() for name in _algo_names_for_header(source_header))


def _status_for(
    *,
    target_exists: bool,
    ledger_status: str | None,
    host_test_exists: bool,
    kernel_spec_exists: bool,
) -> str:
    if not target_exists:
        return "pending"
    status = "generated"
    if ledger_status in _LEDGER_STATUSES:
        status = ledger_status
    elif host_test_exists:
        status = "generated"
    if status == "pending":
        status = "generated"
    if status == "host_passed" and kernel_spec_exists and ledger_status == "kernel_passed":
        status = "kernel_passed"
    return status


def _manual_coverage_target(
    dependency: str,
    *,
    target_root: Path,
    target_repo_prefix: str,
    policy: MigrationPolicy,
) -> str | None:
    covered_by = policy.bootstrap_manual_coverage.get(dependency)
    if not covered_by:
        return None
    target_relpath = normalize_path_str(target_repo_prefix).rstrip("/") + "/" + covered_by
    if (target_root / target_relpath).exists():
        return target_relpath
    return None


def _target_only_wrapper_covers(
    dependency: str,
    *,
    target_root: Path,
    target_repo_prefix: str,
    policy: MigrationPolicy,
) -> str | None:
    if dependency not in policy.target_only_compatibility_wrappers:
        return None
    target_relpath = target_relpath_for_header(dependency, target_repo_prefix=target_repo_prefix)
    if (target_root / target_relpath).exists():
        return target_relpath
    return None


def _classify_missing_dependency(
    *,
    header: str,
    dependency: str,
    target_root: Path,
    target_repo_prefix: str,
    policy: MigrationPolicy,
) -> tuple[str, str]:
    # 整树扫描下 std 头键为 `std/...`；策略键以 cuda/std 命名空间为基准，归一后再匹配。
    header = policy_key(header)
    dependency = policy_key(dependency)
    if header in policy.public_aggregation_headers:
        return (
            "public_aggregation_narrowed",
            "public aggregation header is intentionally limited to validated ACCL components",
        )

    covered_by = _manual_coverage_target(
        dependency,
        target_root=target_root,
        target_repo_prefix=target_repo_prefix,
        policy=policy,
    )
    if covered_by:
        return ("bootstrap_manual", f"covered by hand-authored ACCL bootstrap header {covered_by}")

    wrapper = _target_only_wrapper_covers(
        dependency,
        target_root=target_root,
        target_repo_prefix=target_repo_prefix,
        policy=policy,
    )
    if wrapper:
        return (
            "target_only_compatibility_wrapper",
            f"covered by ACCL compatibility wrapper {wrapper}",
        )

    if dependency.startswith(tuple(policy.deferred_upstream_support_prefixes)):
        return (
            "deferred_upstream_support_only",
            "upstream support/config surface is deferred until a direct migration need is selected",
        )

    return ("true_dependency_gap", "dependency target is missing and must be migrated or replaced")


def _target_only_classification(source_like: str, policy: MigrationPolicy) -> str:
    if source_like in set(policy.bootstrap_manual_coverage.values()):
        return "bootstrap_manual"
    if source_like in policy.target_only_compatibility_wrappers:
        return "target_only_compatibility_wrapper"
    return "target_only"


def _test_kind_counts(mapped_tests: list[str], test_kind_by_path: dict[str, str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for test in mapped_tests:
        kind = test_kind_by_path.get(test)
        if kind:
            counts[kind] = counts.get(kind, 0) + 1
    return dict(sorted(counts.items()))


def _dependency_closure(header: str, dep_map: dict[str, list[str]]) -> list[str]:
    seen: set[str] = set()
    order: list[str] = []

    def visit(node: str) -> None:
        for dep in dep_map.get(node, []):
            if dep in seen:
                continue
            seen.add(dep)
            visit(dep)
            order.append(dep)

    visit(header)
    return sorted(order)


def _candidate_suitability(test_kind_counts: dict[str, int]) -> tuple[str, str, list[str]]:
    reasons: list[str] = []
    pass_count = test_kind_counts.get("pass", 0)
    fail_count = test_kind_counts.get("fail", 0)
    verify_count = test_kind_counts.get("verify", 0)
    if pass_count:
        host = "has_pass_tests"
        kernel = "kernel_candidate_needs_spec_review"
        reasons.append("has_pass_tests")
    elif fail_count or verify_count:
        host = "compile_or_verify_only"
        kernel = "not_kernel_ready"
        reasons.append("has_no_pass_tests")
    else:
        host = "needs_test_mapping_or_substitute"
        kernel = "needs_kernel_suitability_review"
        reasons.append("has_no_mapped_tests")
    return host, kernel, reasons


def _classify_candidate_dependency_counts(
    *,
    header: str,
    closure: list[str],
    target_root: Path,
    target_repo_prefix: str,
    segment_substitutions: list[dict] | None,
    policy: MigrationPolicy,
) -> dict[str, int]:
    counts = {name: 0 for name in MISSING_DEPENDENCY_CLASSIFICATIONS}
    for dep in closure:
        dep_target = target_relpath_for_header(
            dep,
            target_repo_prefix=target_repo_prefix,
            segment_substitutions=segment_substitutions,
        )
        if (target_root / dep_target).exists():
            continue
        classification, _ = _classify_missing_dependency(
            header=header,
            dependency=dep,
            target_root=target_root,
            target_repo_prefix=target_repo_prefix,
            policy=policy,
        )
        counts[classification] += 1
    return counts


def _candidate_score(
    *,
    header: HeaderMigrationStatusEntry,
    closure_size: int,
    missing_counts: dict[str, int],
    test_kind_counts: dict[str, int],
    reasons: list[str],
) -> int:
    score = 100
    if header.shape == "public":
        score -= 45
        reasons.append("public_facade_deferred_until_internals_ready")
    if header.module == "__algorithm":
        score += 30
        reasons.append("algorithm_module")
    elif header.module in {"__numeric", "__utility", "__functional", "__type_traits"}:
        score += 12
        reasons.append("foundational_or_numeric_module")

    pass_count = test_kind_counts.get("pass", 0)
    fail_count = test_kind_counts.get("fail", 0)
    verify_count = test_kind_counts.get("verify", 0)
    score += min(pass_count, 3) * 15
    score -= (fail_count + verify_count) * 10
    score -= closure_size * 2
    score -= missing_counts["true_dependency_gap"] * 18
    score -= missing_counts["deferred_upstream_support_only"] * 4
    score -= missing_counts["bootstrap_manual"] * 1
    if not pass_count and (fail_count or verify_count):
        score -= 20
    if not header.mapped_tests:
        score -= 8
    if missing_counts["true_dependency_gap"] == 0:
        reasons.append("dependency_closure_available_or_ignorable")
    else:
        reasons.append("has_true_dependency_gaps")
    return score


def _build_batch_candidates(
    *,
    headers: list[HeaderMigrationStatusEntry],
    dep_map: dict[str, list[str]],
    test_kind_by_path: dict[str, str],
    target_root: Path,
    target_repo_prefix: str,
    segment_substitutions: list[dict] | None,
    policy: MigrationPolicy,
) -> list[BatchCandidateEntry]:
    candidates: list[BatchCandidateEntry] = []
    for header in headers:
        if header.status != "pending" or header.target_exists:
            continue
        candidate_key = policy_key(header.source_header)
        if candidate_key in policy.public_aggregation_headers:
            continue
        if candidate_key.startswith(tuple(policy.deferred_upstream_support_prefixes)):
            continue
        closure = _dependency_closure(header.source_header, dep_map)
        missing_counts = _classify_candidate_dependency_counts(
            header=header.source_header,
            closure=closure,
            target_root=target_root,
            target_repo_prefix=target_repo_prefix,
            segment_substitutions=segment_substitutions,
            policy=policy,
        )
        test_counts = _test_kind_counts(header.mapped_tests, test_kind_by_path)
        host_suitability, kernel_suitability, reasons = _candidate_suitability(test_counts)
        score = _candidate_score(
            header=header,
            closure_size=len(closure),
            missing_counts=missing_counts,
            test_kind_counts=test_counts,
            reasons=reasons,
        )
        candidates.append(
            BatchCandidateEntry(
                source_header=header.source_header,
                include=header.include,
                module=header.module,
                shape=header.shape,
                target_relpath=header.target_relpath,
                status=header.status,
                dependency_closure_size=len(closure),
                true_missing_dependency_count=missing_counts["true_dependency_gap"],
                classified_missing_dependency_counts=missing_counts,
                mapped_tests=list(header.mapped_tests),
                test_kind_counts=test_counts,
                host_test_suitability=host_suitability,
                kernel_test_suitability=kernel_suitability,
                target_exists=header.target_exists,
                host_test_exists=header.host_test_exists,
                kernel_spec_exists=header.kernel_spec_exists,
                score=score,
                rank_reasons=sorted(set(reasons)),
            )
        )
    return sorted(
        candidates,
        key=lambda item: (
            -item.score,
            item.true_missing_dependency_count,
            item.dependency_closure_size,
            item.source_header,
        ),
    )


def _ledger_map(entries: list[LedgerStatusEntry]) -> dict[str, str]:
    return {entry.key: entry.status for entry in entries}


def _max_status(*candidates: str | None) -> str | None:
    """在若干候选状态里取「最高已确认」的一个（用于合并 ledger 与自动状态证据）。"""
    best: str | None = None
    best_rank = -1
    for candidate in candidates:
        rank = _STATUS_RANK.get(candidate or "", -1)
        if rank > best_rank:
            best, best_rank = candidate, rank
    return best


def build_migration_status_report(
    *,
    inventory: HeaderInventoryReport,
    test_index: CCCLTestIndexReport,
    dep_graph: HeaderDependencyGraphReport,
    target_repo: str | Path,
    ledger_path: str | Path | None = None,
    target_repo_prefix: str = _TARGET_STD_PREFIX,
    segment_substitutions: list[dict] | None = None,
    state_status_map: dict[str, str] | None = None,
    policy: MigrationPolicy | None = None,
) -> MigrationStatusReport:
    """汇总迁移状态报告。

    `state_status_map`（可选）：由 `core.analysis.migration_state` 自动维护的 {source_header: status}
    验证证据（host/kernel 实测通过 + 源未变）。它与手写 ledger **同级**参与状态判定，取二者
    里更高的已确认状态。这让 闭包能在没有手写 ledger 的情况下识别「已验证、可跳过」的依赖。
    """
    target_root = Path(target_repo).resolve()
    policy = policy or default_migration_policy()
    # include 命名空间随头根（cuda/std 标准库层 或 cuda 扩展层）。
    namespace = namespace_for_root(inventory.header_root)
    target_inventory: TargetHeaderInventoryReport = scan_target_header_inventory(
        target_root,
        target_repo_prefix=target_repo_prefix,
    )
    target_health_by_std_relpath = {
        entry.std_relpath: entry
        for entry in target_inventory.headers
    }
    ledger_entries = parse_migration_ledger_statuses(ledger_path) if ledger_path else []
    ledger = _ledger_map(ledger_entries)
    state_status_map = state_status_map or {}
    test_map = {mapping.header: mapping.tests for mapping in test_index.mappings}
    test_kind_by_path = {entry.relative_path: entry.kind for entry in test_index.tests}
    dep_map = {entry.header: entry.dependencies for entry in dep_graph.graph}

    headers: list[HeaderMigrationStatusEntry] = []
    missing_dependencies: list[MissingDependencyEntry] = []
    source_target_relpaths: set[str] = set()

    for header in sorted(inventory.headers, key=lambda h: h.relative_path):
        target_relpath = target_relpath_for_header(
            header.relative_path,
            target_repo_prefix=target_repo_prefix,
            segment_substitutions=segment_substitutions,
        )
        source_target_relpaths.add(target_relpath)
        target_exists = (target_root / target_relpath).exists()
        target_std_relpath = target_relpath.split(
            normalize_path_str(target_repo_prefix).rstrip("/") + "/",
            1,
        )[-1]
        target_health = target_health_by_std_relpath.get(target_std_relpath)
        target_include_missing = (
            list(target_health.missing_include_dependencies)
            if target_health is not None
            else []
        )
        host_exists = _host_test_exists(target_root, header.relative_path)
        kernel_exists = _kernel_spec_exists(target_root, header.relative_path)
        ledger_status = ledger.get(header.relative_path) or ledger.get(target_relpath)
        state_status = state_status_map.get(header.relative_path)
        # ledger（手写）与 state（自动验证证据）同级，取更高的已确认状态参与判定。
        evidence_status = _max_status(ledger_status, state_status)
        status = _status_for(
            target_exists=target_exists,
            ledger_status=evidence_status,
            host_test_exists=host_exists,
            kernel_spec_exists=kernel_exists,
        )
        notes: list[str] = []
        if evidence_status and not target_exists:
            notes.append("ledger_status_ignored_because_target_header_is_missing")
        if (
            target_exists
            and state_status
            and _STATUS_RANK.get(state_status, -1) >= _STATUS_RANK.get(ledger_status or "", -1)
            and state_status in _LEDGER_STATUSES
        ):
            notes.append("validated_via_state_store")
        if target_include_missing:
            notes.append("target_header_has_missing_includes")

        deps = dep_map.get(header.relative_path, [])
        missing: list[str] = []
        for dep in deps:
            dep_target = target_relpath_for_header(
                dep,
                target_repo_prefix=target_repo_prefix,
                segment_substitutions=segment_substitutions,
            )
            if target_exists and not (target_root / dep_target).exists():
                classification, reason = _classify_missing_dependency(
                    header=header.relative_path,
                    dependency=dep,
                    target_root=target_root,
                    target_repo_prefix=target_repo_prefix,
                    policy=policy,
                )
                missing.append(dep)
                missing_dependencies.append(
                    MissingDependencyEntry(
                        header=header.relative_path,
                        dependency=dep,
                        dependency_target_relpath=dep_target,
                        classification=classification,
                        reason=reason,
                    )
                )

        headers.append(
            HeaderMigrationStatusEntry(
                source_header=header.relative_path,
                include=f"{namespace}/{header.relative_path}",
                module=header.module,
                shape=header.shape,
                target_relpath=target_relpath,
                target_exists=target_exists,
                status=status,
                ledger_status=ledger_status,
                host_test_exists=host_exists,
                kernel_spec_exists=kernel_exists,
                target_include_missing_dependencies=sorted(target_include_missing),
                dependencies=list(deps),
                missing_dependencies=sorted(missing),
                mapped_tests=test_map.get(header.relative_path, []),
                notes=notes,
            )
        )

    target_only_headers: list[TargetOnlyHeaderEntry] = []
    for path in _target_header_paths(target_root, target_repo_prefix):
        relpath = _target_header_relpath(path, target_root)
        if relpath in source_target_relpaths:
            continue
        source_like = relpath.split(normalize_path_str(target_repo_prefix).rstrip("/") + "/", 1)[-1]
        ledger_status = ledger.get(relpath) or ledger.get(source_like)
        host_exists = _host_test_exists(target_root, source_like)
        kernel_exists = _kernel_spec_exists(target_root, source_like)
        target_only_headers.append(
            TargetOnlyHeaderEntry(
                target_relpath=relpath,
                status=_status_for(
                    target_exists=True,
                    ledger_status=ledger_status,
                    host_test_exists=host_exists,
                    kernel_spec_exists=kernel_exists,
                ),
                ledger_status=ledger_status,
                host_test_exists=host_exists,
                kernel_spec_exists=kernel_exists,
                classification=_target_only_classification(source_like, policy),
            )
        )

    batch_candidates = _build_batch_candidates(
        headers=headers,
        dep_map=dep_map,
        test_kind_by_path=test_kind_by_path,
        target_root=target_root,
        target_repo_prefix=target_repo_prefix,
        segment_substitutions=segment_substitutions,
        policy=policy,
    )

    return MigrationStatusReport(
        cccl_repo=inventory.cccl_repo,
        header_root=inventory.header_root,
        test_root=test_index.test_root,
        target_repo=str(target_root),
        headers=headers,
        target_only_headers=target_only_headers,
        missing_dependencies=sorted(
            missing_dependencies,
            key=lambda item: (item.header, item.dependency),
        ),
        mapped_tests=[mapping.to_dict() for mapping in test_index.mappings],
        unmapped_tests=list(test_index.unmapped_tests),
        unmapped_headers=list(test_index.unmapped_headers),
        ledger_entries=ledger_entries,
        dep_graph_cycles=[list(cycle) for cycle in dep_graph.cycles],
        batch_candidates=batch_candidates,
        target_headers=[entry.to_dict() for entry in target_inventory.headers],
    )


def scan_migration_status(
    cccl_repo: str | Path | None,
    *,
    target_repo: str | Path,
    ledger_path: str | Path | None = None,
    target_repo_prefix: str = _TARGET_STD_PREFIX,
    segment_substitutions: list[dict] | None = None,
    symbol_dependency_rules: Sequence[Mapping] | None = None,
    include_root_rel: str | Path = HEADER_ROOT_REL,
    test_root_rel: str | Path = TEST_ROOT_REL,
) -> MigrationStatusReport:
    inventory = scan_header_inventory(
        cccl_repo, include_root_rel=include_root_rel, symbol_dependency_rules=symbol_dependency_rules
    )
    test_index = scan_test_index(cccl_repo, include_root_rel=include_root_rel, test_root_rel=test_root_rel)
    dep_graph = scan_dependency_graph(
        cccl_repo, include_root_rel=include_root_rel, symbol_dependency_rules=symbol_dependency_rules
    )
    return build_migration_status_report(
        inventory=inventory,
        test_index=test_index,
        dep_graph=dep_graph,
        target_repo=target_repo,
        ledger_path=ledger_path,
        target_repo_prefix=target_repo_prefix,
        segment_substitutions=segment_substitutions,
    )


def write_migration_status_report(
    report: MigrationStatusReport,
    output_dir: str | Path,
    *,
    filename: str = DEFAULT_MIGRATION_STATUS_REPORT_NAME,
) -> Path:
    name = Path(filename)
    if name.is_absolute() or len(name.parts) != 1:
        raise ValueError("migration status report filename must be a file name under outputs/")
    path = Path(output_dir) / name
    payload = json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
    save_text(path, payload + "\n")
    return path
