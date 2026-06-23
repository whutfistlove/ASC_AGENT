"""Whole-package dependency-wave migration planning (deterministic, no model).

`folder_planner` recommends batches within one folder, but its follow-up batches
are complexity-sorted fixed-size chunks that do **not** guarantee "all of my
dependencies live in earlier batches". That is the pain point behind hard
single-closure migrations: a header can be fed to the model before its
dependencies exist.

This module analyses the **entire** source CCCL library and produces a strictly
dependency-ordered batch plan (waves): batch-1 are leaves, batch-N only depends
on batches < N. The plan is a living ledger — every header that migrates
successfully (semantic tests passed, recorded in ``migration_state.json``) is
marked done; re-running drops completed headers from the waves and pulls their
dependents forward. Cycles (strongly connected components) are co-located in one
batch so they can be migrated together.

It reuses existing facts and never calls the model:
  * dependency edges / cycles  -> :mod:`core.analysis.dep_graph`
  * per-header status / policy  -> :mod:`core.analysis.migration_status`
  * validated-state evidence    -> :mod:`core.analysis.migration_state`
  * complexity scoring          -> :mod:`core.planning.folder_planner`
"""

from __future__ import annotations

import json
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

from core.analysis.dep_graph import HeaderDependencyGraphReport
from core.analysis.inventory import HeaderInventoryReport, namespace_for_root
from core.analysis.migration_status import MigrationStatusReport
from core.analysis.test_index import CCCLTestIndexReport
from core.common.config import Config
from core.common.utils import save_text
from core.planning.folder_planner import (
    _complexity_label,
    _complexity_score,
    _dependency_closure,
    _source_stats,
)

DEFAULT_PACKAGE_PLAN_JSON = "package_migration_plan.json"
DEFAULT_PACKAGE_PLAN_MD = "package_migration_plan.md"
# 与 pipeline.SAFE_DEPENDENCY_SKIP_STATUSES / migration_state.VALIDATED_STATUSES 对齐。
SAFE_STATUSES = frozenset({"host_passed", "kernel_passed", "full_passed"})
SCHEMA_VERSION = 1
MARKDOWN_BATCH_HEADER_LIMIT = 80
MARKDOWN_LIST_LIMIT = 40


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- #
# 分类：completed / deferred / pending
# --------------------------------------------------------------------------- #
def _policy_deferred(header: str, config: Config) -> tuple[bool, str]:
    """命中 migration_policy 的头不走常规波次（由手写 bootstrap/伞头/兼容包装覆盖）。

    口径与 migration_status._build_batch_candidates 的排除项一致：公开伞头、
    延期上游支撑前缀、bootstrap 手写覆盖键。target-only 兼容包装头仍可正常迁移
    （与 batch_candidates 一致），不在此延期。
    """
    policy = config.migration_policy
    if header in policy.public_aggregation_headers:
        return True, "public_aggregation"
    if header.startswith(tuple(policy.deferred_upstream_support_prefixes)):
        return True, "deferred_upstream_support"
    if header in policy.bootstrap_manual_coverage:
        return True, "bootstrap_manual"
    return False, ""


def reconcile_completed(
    status_report: MigrationStatusReport, manual_marks: set[str] | None = None
) -> set[str]:
    """合并「自动验证证据」与「人工标记」为已完成集合。

    自动证据：status_report 中 status ∈ SAFE_STATUSES（已折入 migration_state 的
    语义通过 + 源新鲜度，且 target 存在）。人工标记：``--mark`` 持久化下来的集合。
    """
    auto = {entry.source_header for entry in status_report.headers if entry.status in SAFE_STATUSES}
    return auto | set(manual_marks or set())


def read_manual_marks(plan_path: str | Path) -> set[str]:
    """从既有计划文件读出持久化的人工标记；文件缺失/损坏返回空集。"""
    p = Path(plan_path)
    if not p.is_file():
        return set()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    if not isinstance(data, dict):
        return set()
    return {str(h) for h in (data.get("manual_marks") or [])}


# --------------------------------------------------------------------------- #
# 强连通分量（迭代式 Tarjan，避免深链递归超限）+ 分层波次
# --------------------------------------------------------------------------- #
def _strongly_connected_components(
    nodes: list[str], adj: dict[str, list[str]]
) -> list[list[str]]:
    index_counter = 0
    index: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    on_stack: dict[str, bool] = {}
    stack: list[str] = []
    components: list[list[str]] = []

    for root in nodes:
        if root in index:
            continue
        work: list[tuple[str, int]] = [(root, 0)]
        while work:
            node, child_i = work[-1]
            if child_i == 0:
                index[node] = lowlink[node] = index_counter
                index_counter += 1
                stack.append(node)
                on_stack[node] = True
            recursed = False
            children = adj.get(node, [])
            i = child_i
            while i < len(children):
                child = children[i]
                if child not in index:
                    work[-1] = (node, i + 1)
                    work.append((child, 0))
                    recursed = True
                    break
                if on_stack.get(child):
                    lowlink[node] = min(lowlink[node], index[child])
                i += 1
            if recursed:
                continue
            if lowlink[node] == index[node]:
                component: list[str] = []
                while True:
                    member = stack.pop()
                    on_stack[member] = False
                    component.append(member)
                    if member == node:
                        break
                components.append(component)
            work.pop()
            if work:
                parent = work[-1][0]
                lowlink[parent] = min(lowlink[parent], lowlink[node])
    return components


def _condensation_waves(
    pending: list[str], blocking_deps: dict[str, list[str]]
) -> tuple[dict[str, int], dict[str, int], list[list[str]]]:
    """返回 (header->wave, header->comp_id, components)。

    wave 为 0-based 分层拓扑层号：叶子（无 pending 依赖）为 0，其余为
    1 + max(依赖所在 comp 的 wave)。环（comp 大小 > 1）成员同 wave。
    """
    components = _strongly_connected_components(pending, blocking_deps)
    comp_id: dict[str, int] = {}
    for cid, comp in enumerate(components):
        for header in comp:
            comp_id[header] = cid

    comp_deps: dict[int, set[int]] = {cid: set() for cid in range(len(components))}
    for header in pending:
        hc = comp_id[header]
        for dep in blocking_deps.get(header, []):
            dc = comp_id[dep]
            if dc != hc:
                comp_deps[hc].add(dc)

    dependents: dict[int, set[int]] = defaultdict(set)
    remaining: dict[int, int] = {}
    for cid, deps in comp_deps.items():
        remaining[cid] = len(deps)
        for dep in deps:
            dependents[dep].add(cid)

    comp_wave: dict[int, int] = {}
    queue: deque[int] = deque()
    for cid, count in remaining.items():
        if count == 0:
            comp_wave[cid] = 0
            queue.append(cid)
    while queue:
        cid = queue.popleft()
        for dependent in dependents[cid]:
            comp_wave[dependent] = max(comp_wave.get(dependent, 0), comp_wave[cid] + 1)
            remaining[dependent] -= 1
            if remaining[dependent] == 0:
                queue.append(dependent)

    header_wave = {header: comp_wave[comp_id[header]] for header in pending}
    return header_wave, comp_id, components


# --------------------------------------------------------------------------- #
# 计划构建
# --------------------------------------------------------------------------- #
def build_package_plan_payload(
    *,
    config: Config,
    inventory: HeaderInventoryReport,
    dep_graph: HeaderDependencyGraphReport,
    test_index: CCCLTestIndexReport,
    status_report: MigrationStatusReport,
    manual_marks: set[str] | None = None,
) -> dict:
    """Build a deterministic whole-package dependency-wave migration plan."""
    manual_marks = set(manual_marks or set())
    header_root = Path(inventory.header_root)
    namespace = namespace_for_root(inventory.header_root)
    dep_by_header = {entry.header: list(entry.dependencies) for entry in dep_graph.graph}
    dep_entries = {entry.header: entry for entry in dep_graph.graph}
    status_by_header = {entry.source_header: entry for entry in status_report.headers}
    inv_by_header = {entry.relative_path: entry for entry in inventory.headers}
    candidate_by_header = {entry.source_header: entry for entry in status_report.batch_candidates}
    test_by_header = {mapping.header: list(mapping.tests) for mapping in test_index.mappings}

    all_headers = sorted(entry.relative_path for entry in inventory.headers)
    completed = reconcile_completed(status_report, manual_marks)

    deferred_entries: list[dict] = []
    deferred_set: set[str] = set()
    pending: list[str] = []
    for header in all_headers:
        if header in completed:
            continue
        is_deferred, classification = _policy_deferred(header, config)
        if is_deferred:
            deferred_set.add(header)
            deferred_entries.append(
                {
                    "source_header": header,
                    "classification": classification,
                    "reason": "covered_by_migration_policy",
                }
            )
            continue
        pending.append(header)

    available = completed | deferred_set

    # 阻塞边：仅指向其它 pending 头的依赖才算阻塞；completed/deferred 视为已就绪。
    pending_set = set(pending)
    blocking_deps: dict[str, list[str]] = {}
    blocked_entries: list[dict] = []
    blocked_set: set[str] = set()
    for header in pending:
        blockers: list[str] = []
        unresolved: list[str] = []
        for dep in dep_by_header.get(header, []):
            if dep in pending_set:
                blockers.append(dep)
            elif dep in available:
                continue
            else:
                # 既非 pending 也非 completed/deferred 的库内依赖：无法解析（防御性，整库下应为空）。
                unresolved.append(dep)
        blocking_deps[header] = blockers
        if unresolved:
            blocked_set.add(header)
            blocked_entries.append(
                {
                    "source_header": header,
                    "unresolved_dependencies": sorted(unresolved),
                    "reason": "depends_on_unresolvable_headers",
                }
            )

    waveable = [header for header in pending if header not in blocked_set]
    blocking_deps_waveable = {
        header: [dep for dep in blocking_deps[header] if dep not in blocked_set]
        for header in waveable
    }
    header_wave, comp_id, components = _condensation_waves(waveable, blocking_deps_waveable)

    def _header_detail(header: str) -> dict:
        status_entry = status_by_header.get(header)
        dep_entry = dep_entries.get(header)
        inv_entry = inv_by_header.get(header)
        candidate = candidate_by_header.get(header)
        deps = dep_by_header.get(header, [])
        closure_size = len(_dependency_closure(header, dep_by_header))
        stats = _source_stats(header_root, header)
        true_missing = candidate.true_missing_dependency_count if candidate else 0
        score = _complexity_score(
            stats=stats,
            direct_deps=len(deps),
            closure_size=closure_size,
            unknown_count=len(dep_entry.unknown_cuda_std_includes) if dep_entry else 0,
            conditional_count=len(inv_entry.conditional_includes) if inv_entry else 0,
            true_missing_dependency_count=true_missing,
        )
        in_cycle = len(components[comp_id[header]]) > 1
        return {
            "source_header": header,
            "target_relpath": status_entry.target_relpath if status_entry else "",
            "include": status_entry.include if status_entry else f"{namespace}/{header}",
            "module": status_entry.module if status_entry else "",
            "complexity_label": _complexity_label(score),
            "complexity_score": score,
            "direct_dependency_count": len(deps),
            "dependency_closure_size": closure_size,
            "true_missing_dependency_count": true_missing,
            "mapped_test_count": len(test_by_header.get(header, [])),
            "in_cycle": in_cycle,
            "status": status_entry.status if status_entry else "pending",
            "migrated": False,
        }

    details = {header: _header_detail(header) for header in waveable}
    by_wave: dict[int, list[str]] = defaultdict(list)
    for header in waveable:
        by_wave[header_wave[header]].append(header)

    batches: list[dict] = []
    for level in sorted(by_wave):
        headers = by_wave[level]
        headers.sort(
            key=lambda h: (
                details[h]["complexity_score"],
                details[h]["true_missing_dependency_count"],
                details[h]["module"],
                h,
            )
        )
        batch_details = [details[h] for h in headers]
        batches.append(
            {
                "name": f"batch-{level + 1}",
                "wave": level + 1,
                "contains_cycle": any(d["in_cycle"] for d in batch_details),
                "header_count": len(batch_details),
                "headers": batch_details,
            }
        )

    cycle_count = sum(1 for comp in components if len(comp) > 1)
    completed_entries = []
    for header in sorted(completed):
        status_entry = status_by_header.get(header)
        completed_entries.append(
            {
                "source_header": header,
                "target_relpath": status_entry.target_relpath if status_entry else "",
                "status": status_entry.status if status_entry else "",
                "evidence": "manual" if (header in manual_marks and (status_entry is None or status_entry.status not in SAFE_STATUSES)) else "validated",
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "approved": False,
        "generated_at": _now_iso(),
        "cccl_repo": inventory.cccl_repo,
        "header_root": inventory.header_root,
        "target_repo": config.target_repo,
        "namespace": namespace,
        "manual_marks": sorted(manual_marks),
        "summary": {
            "total_headers": len(all_headers),
            "completed": len(completed),
            "pending": len(waveable),
            "deferred": len(deferred_entries),
            "blocked": len(blocked_entries),
            "batch_count": len(batches),
            "cycle_count": cycle_count,
        },
        "batches": batches,
        "completed_headers": completed_entries,
        "deferred_headers": sorted(deferred_entries, key=lambda item: item["source_header"]),
        "blocked_headers": sorted(blocked_entries, key=lambda item: item["source_header"]),
    }


# --------------------------------------------------------------------------- #
# 批次解析 / 标记
# --------------------------------------------------------------------------- #
def _all_plan_headers(plan: dict) -> set[str]:
    headers: set[str] = set()
    for batch in plan.get("batches") or []:
        for item in batch.get("headers") or []:
            if item.get("source_header"):
                headers.add(item["source_header"])
    return headers


def headers_for_batch(plan: dict, batch: str, completed: set[str] | None = None) -> list[str]:
    """Resolve a batch selector to an ordered, not-yet-completed header list.

    Selectors: ``batch-N`` / ``next`` (first batch still holding uncompleted
    headers) / ``all`` / comma-separated explicit header list.
    """
    completed = set(completed or set())
    batches = plan.get("batches") or []

    def uncompleted(headers: list[str]) -> list[str]:
        return [h for h in headers if h not in completed]

    def batch_headers(entry: dict) -> list[str]:
        return [item["source_header"] for item in entry.get("headers") or [] if item.get("source_header")]

    if batch == "all":
        out: list[str] = []
        for entry in batches:
            for header in uncompleted(batch_headers(entry)):
                if header not in out:
                    out.append(header)
        return out
    if batch == "next":
        for entry in batches:
            todo = uncompleted(batch_headers(entry))
            if todo:
                return todo
        return []
    if batch.startswith("batch-"):
        for entry in batches:
            if entry.get("name") == batch:
                return uncompleted(batch_headers(entry))
        return []
    explicit = [item.strip() for item in batch.split(",") if item.strip()]
    known = _all_plan_headers(plan)
    return [header for header in explicit if header in known and header not in completed]


def plan_completed_set(plan: dict) -> set[str]:
    return {
        item["source_header"]
        for item in plan.get("completed_headers") or []
        if item.get("source_header")
    }


# --------------------------------------------------------------------------- #
# 落盘 / Markdown
# --------------------------------------------------------------------------- #
def plan_to_markdown(plan: dict, *, json_name: str = DEFAULT_PACKAGE_PLAN_JSON) -> str:
    summary = plan["summary"]
    lines: list[str] = []
    lines.append("# Package Migration Plan (dependency waves)")
    lines.append("")
    lines.append(f"- approved: `{plan.get('approved', False)}`")
    lines.append(f"- generated_at: `{plan.get('generated_at', '')}`")
    lines.append(f"- cccl_repo: `{plan['cccl_repo']}`")
    lines.append(f"- target_repo: `{plan['target_repo']}`")
    lines.append(f"- execution_json: `outputs/{json_name}`")
    lines.append(
        f"- headers: {summary['total_headers']}, completed: {summary['completed']}, "
        f"pending: {summary['pending']}, deferred: {summary['deferred']}, blocked: {summary['blocked']}"
    )
    lines.append(f"- batches: {summary['batch_count']}, cycles: {summary['cycle_count']}")
    lines.append("")
    lines.append("## Batches (migrate in order; each batch depends only on earlier batches)")
    for batch in plan.get("batches") or []:
        flag = " ⟲cycle" if batch.get("contains_cycle") else ""
        lines.append("")
        lines.append(f"### {batch['name']} (wave {batch['wave']}, {batch['header_count']} headers){flag}")
        for item in (batch.get("headers") or [])[:MARKDOWN_BATCH_HEADER_LIMIT]:
            mark = "x" if item.get("migrated") else " "
            cyc = " [cycle]" if item.get("in_cycle") else ""
            lines.append(
                f"- [{mark}] `{item['source_header']}` -> `{item['target_relpath']}` "
                f"({item['complexity_label']}, score={item['complexity_score']}, "
                f"deps={item['dependency_closure_size']}, tests={item['mapped_test_count']}){cyc}"
            )
        extra = batch["header_count"] - MARKDOWN_BATCH_HEADER_LIMIT
        if extra > 0:
            lines.append(f"- ... +{extra} more headers; see JSON.")
    lines.append("")
    lines.append(f"## Completed ({summary['completed']})")
    for item in (plan.get("completed_headers") or [])[:MARKDOWN_LIST_LIMIT]:
        lines.append(f"- [x] `{item['source_header']}` ({item.get('status', '')}, {item.get('evidence', '')})")
    if summary["completed"] > MARKDOWN_LIST_LIMIT:
        lines.append(f"- ... +{summary['completed'] - MARKDOWN_LIST_LIMIT} more; see JSON.")
    lines.append("")
    lines.append(f"## Deferred by policy ({summary['deferred']})")
    for item in (plan.get("deferred_headers") or [])[:MARKDOWN_LIST_LIMIT]:
        lines.append(f"- `{item['source_header']}` ({item['classification']})")
    if summary["deferred"] > MARKDOWN_LIST_LIMIT:
        lines.append(f"- ... +{summary['deferred'] - MARKDOWN_LIST_LIMIT} more; see JSON.")
    if plan.get("blocked_headers"):
        lines.append("")
        lines.append(f"## Blocked ({summary['blocked']})")
        for item in plan["blocked_headers"][:MARKDOWN_LIST_LIMIT]:
            lines.append(
                f"- `{item['source_header']}`: unresolved={', '.join(item.get('unresolved_dependencies') or [])}"
            )
    lines.append("")
    lines.append("## How To Run After Review")
    lines.append("```bash")
    lines.append(
        f"python3 main.py package-migrate --plan outputs/{json_name} --batch next --approve "
        "--real-ai --with-tests --test-feedback-to-model"
    )
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def write_package_plan(
    plan: dict,
    output_dir: str | Path,
    *,
    json_name: str = DEFAULT_PACKAGE_PLAN_JSON,
    md_name: str = DEFAULT_PACKAGE_PLAN_MD,
) -> tuple[Path, Path]:
    for name in (json_name, md_name):
        candidate = Path(name)
        if candidate.is_absolute() or len(candidate.parts) != 1:
            raise ValueError("package plan filename must be a file name under outputs/")
    out = Path(output_dir)
    json_path = out / json_name
    md_path = out / md_name
    save_text(json_path, json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    save_text(md_path, plan_to_markdown(plan, json_name=json_name) + "\n")
    return json_path, md_path


def load_package_plan(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"not a package migration plan v{SCHEMA_VERSION}: {path}")
    return data
