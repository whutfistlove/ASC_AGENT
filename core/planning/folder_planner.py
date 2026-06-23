"""Folder-level migration planning.

This module turns a source folder under libcudacxx/include/cuda/std into a
reviewable migration plan: dependency facts, complexity/risk hints, deterministic
batch suggestions, and optional model-refined recommendations.
"""

from __future__ import annotations

import copy
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.analysis.dep_graph import HeaderDependencyGraphReport
from core.analysis.inventory import HEADER_ROOT_REL, HeaderInventoryReport, namespace_for_root
from core.analysis.migration_status import MigrationStatusReport, target_relpath_for_header
from core.analysis.test_index import CCCLTestIndexReport
from core.common.config import Config
from core.common.utils import save_text
from core.llm.model_client import BaseModelClient, extract_json_object

DEFAULT_FOLDER_PLAN_JSON = "folder_migration_plan.json"
DEFAULT_FOLDER_PLAN_DETAILS_JSON = "folder_migration_plan_details.json"
DEFAULT_FOLDER_PLAN_MD = "folder_migration_plan.md"
SAFE_DEPENDENCY_STATUSES = {"host_passed", "kernel_passed", "full_passed"}
MARKDOWN_TOP_DEPENDENCIES = 12
MARKDOWN_HEADER_SAMPLES = 20
JSON_DEPENDENCY_PREVIEW_LIMIT = 12


@dataclass(frozen=True)
class FolderPlanOptions:
    first_batch_size: int = 5
    followup_batch_size: int = 8
    max_ai_candidates: int = 80


def _strip_known_prefix(value: str, namespace: str = "cuda/std") -> str:
    """Strip a namespace prefix (`cuda/std` 或 `cuda`) from a user source-dir."""
    text = value.replace("\\", "/").strip("/")
    ns = namespace.strip("/")
    last = ns.split("/")[-1]
    roots = {
        f"libcudacxx/include/{ns}",
        f"include/{ns}",
        ns,
        last,
        ".",
        "",
    }
    if text in roots:
        return ""

    embedded_header_root = f"libcudacxx/include/{ns}/"
    if embedded_header_root in text:
        return text.split(embedded_header_root, 1)[1].strip("/")

    prefixes = (
        f"libcudacxx/include/{ns}/",
        f"include/{ns}/",
        f"{ns}/",
        f"{last}/",
    )
    for prefix in prefixes:
        if text.startswith(prefix):
            return text[len(prefix):].strip("/")
    return text


def folder_scope_relpath(source_dir: str | Path, *, header_root: str | Path) -> str:
    """Resolve a user folder path to a namespace-relative folder path.

    命名空间随 header_root（`cuda/std` 标准库层 或 `cuda` 扩展层）自动推导。
    """
    raw = Path(source_dir)
    root = Path(header_root).resolve()
    namespace = namespace_for_root(header_root)
    if raw.is_absolute():
        resolved = raw.resolve()
        if resolved.is_file():
            resolved = resolved.parent
        try:
            relpath = resolved.relative_to(root).as_posix().strip("/")
            return "" if relpath == "." else relpath
        except ValueError as exc:
            raise ValueError(f"source-dir must be under CCCL header root: {root}") from exc
    return _strip_known_prefix(str(source_dir), namespace)


def _in_scope(header: str, scope: str) -> bool:
    if not scope:
        return True
    return header == scope or header.startswith(scope.rstrip("/") + "/")


def _dep_entry_map(dep_graph: HeaderDependencyGraphReport) -> dict[str, Any]:
    return {entry.header: entry for entry in dep_graph.graph}


def _closure_size(header: str, dep_map: dict[str, list[str]]) -> int:
    return len(_dependency_closure(header, dep_map))


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
    return order


def _target_header_health(status_report: MigrationStatusReport) -> dict[str, dict]:
    return {
        str(entry.get("std_relpath")): entry
        for entry in status_report.target_headers
        if isinstance(entry, dict) and entry.get("std_relpath")
    }


def _policy_dependency_item(config: Config, dependency: str) -> dict | None:
    policy = config.migration_policy
    target_root = Path(config.target_repo)
    if dependency in policy.bootstrap_manual_coverage:
        covered = policy.bootstrap_manual_coverage[dependency]
        target_relpath = target_relpath_for_header(
            covered,
            target_repo_prefix=config.target_repo_prefix,
            segment_substitutions=config.segment_substitutions,
        )
        if (target_root / target_relpath).exists():
            return {
                "classification": "bootstrap_manual",
                "dependency": dependency,
                "reason": f"covered_by:{covered}",
                "target_relpath": target_relpath,
            }
    if dependency in policy.target_only_compatibility_wrappers:
        target_relpath = target_relpath_for_header(
            dependency,
            target_repo_prefix=config.target_repo_prefix,
            segment_substitutions=config.segment_substitutions,
        )
        if (target_root / target_relpath).exists():
            return {
                "classification": "target_only_compatibility_wrapper",
                "dependency": dependency,
                "reason": "covered_by_target_only_wrapper",
                "target_relpath": target_relpath,
            }
    if dependency.startswith(tuple(policy.deferred_upstream_support_prefixes)):
        return {
            "classification": "deferred_upstream_support_only",
            "dependency": dependency,
            "reason": "deferred_by_migration_policy",
            "target_relpath": target_relpath_for_header(
                dependency,
                target_repo_prefix=config.target_repo_prefix,
                segment_substitutions=config.segment_substitutions,
            ),
        }
    return None


def _dependency_item(
    *,
    dependency: str,
    status_by_header: dict,
    target_health_by_std_relpath: dict[str, dict],
    config: Config,
) -> dict:
    status = status_by_header.get(dependency)
    target_relpath = (
        status.target_relpath
        if status is not None
        else target_relpath_for_header(
            dependency,
            target_repo_prefix=config.target_repo_prefix,
            segment_substitutions=config.segment_substitutions,
        )
    )
    target_health = target_health_by_std_relpath.get(dependency) or {}
    missing_includes = list(target_health.get("missing_include_dependencies") or [])
    target_exists = bool(status.target_exists) if status is not None else bool(target_health)
    status_value = status.status if status is not None else ("generated" if target_exists else "pending")
    return {
        "dependency": dependency,
        "target_relpath": target_relpath,
        "target_exists": target_exists,
        "status": status_value,
        "safe_status": status_value in SAFE_DEPENDENCY_STATUSES,
        "target_include_missing_dependencies": missing_includes,
    }


def _external_dependency_groups(
    *,
    closure: list[str],
    scope: str,
    status_by_header: dict,
    target_health_by_std_relpath: dict[str, dict],
    config: Config,
) -> dict:
    groups = {
        "external_satisfied_dependencies": [],
        "external_unverified_dependencies": [],
        "external_missing_dependencies": [],
        "external_broken_dependencies": [],
        "policy_deferred_dependencies": [],
    }
    for dep in closure:
        if _in_scope(dep, scope):
            continue
        item = _dependency_item(
            dependency=dep,
            status_by_header=status_by_header,
            target_health_by_std_relpath=target_health_by_std_relpath,
            config=config,
        )
        if item["target_exists"]:
            if item["target_include_missing_dependencies"]:
                groups["external_broken_dependencies"].append(item)
            elif item["safe_status"]:
                groups["external_satisfied_dependencies"].append(item)
            else:
                groups["external_unverified_dependencies"].append(item)
            continue
        policy_item = _policy_dependency_item(config, dep)
        if policy_item:
            groups["policy_deferred_dependencies"].append({**item, **policy_item})
        else:
            groups["external_missing_dependencies"].append(item)
    return groups


def _external_approval_required(groups: dict) -> bool:
    return bool(
        groups["external_unverified_dependencies"]
        or groups["external_missing_dependencies"]
        or groups["external_broken_dependencies"]
    )


def _source_stats(header_root: Path, header: str) -> dict:
    path = header_root / header
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    return {
        "line_count": len(text.splitlines()),
        "template_count": len(re.findall(r"\btemplate\s*<", text)),
        "preprocessor_count": len(re.findall(r"^\s*#", text, flags=re.MULTILINE)),
        "cccl_macro_count": len(re.findall(r"\b_CCCL_[A-Z0-9_]+\b", text)),
        "cuda_std_qualified_count": text.count("::cuda::std::") + text.count("_CUDA_VSTD::"),
        "branch_count": len(re.findall(r"\b(if|else|switch|for|while)\b", text)),
    }


def _complexity_label(score: int) -> str:
    if score <= 18:
        return "easy"
    if score <= 45:
        return "medium"
    return "hard"


def _complexity_score(*, stats: dict, direct_deps: int, closure_size: int,
                      unknown_count: int, conditional_count: int,
                      true_missing_dependency_count: int) -> int:
    return (
        max(0, stats["line_count"] // 80)
        + stats["template_count"] * 2
        + stats["cccl_macro_count"]
        + stats["cuda_std_qualified_count"]
        + stats["branch_count"]
        + direct_deps * 2
        + closure_size
        + unknown_count * 3
        + conditional_count * 2
        + true_missing_dependency_count * 4
    )


def _cycle_nodes(dep_graph: HeaderDependencyGraphReport) -> set[str]:
    out: set[str] = set()
    for cycle in dep_graph.cycles:
        out.update(cycle)
    return out


def _chunk(seq: list[str], size: int) -> list[list[str]]:
    size = max(1, size)
    return [seq[i:i + size] for i in range(0, len(seq), size)]


def _analysis_reason(entry: dict) -> list[str]:
    reasons: list[str] = []
    if entry["status"] != "pending":
        reasons.append(f"status={entry['status']}")
    if entry["target_exists"]:
        reasons.append("target_exists")
    if entry["in_cycle"]:
        reasons.append("dependency_cycle")
    if entry["true_missing_dependency_count"]:
        reasons.append(f"true_missing_dependencies={entry['true_missing_dependency_count']}")
    else:
        reasons.append("dependency_closure_available")
    if entry["symbol_dependency_count"]:
        reasons.append(f"symbol_dependencies={entry['symbol_dependency_count']}")
    if entry.get("external_dependency_issue_count"):
        reasons.append(f"external_dependencies_need_approval={entry['external_dependency_issue_count']}")
    if entry.get("external_satisfied_dependency_count"):
        reasons.append(f"external_dependencies_verified={entry['external_satisfied_dependency_count']}")
    if entry.get("policy_deferred_dependency_count"):
        reasons.append(f"policy_deferred_dependencies={entry['policy_deferred_dependency_count']}")
    if entry["dependency_closure_size"] == 0:
        reasons.append("leaf_or_no_in_tree_dependencies")
    elif entry["dependency_closure_size"] <= 2:
        reasons.append(f"small_dependency_closure={entry['dependency_closure_size']}")
    if entry["mapped_test_count"]:
        reasons.append(f"mapped_tests={entry['mapped_test_count']}")
    if entry["host_test_suitability"] == "has_pass_tests":
        reasons.append("has_pass_tests")
    if entry["complexity_label"] == "easy":
        reasons.append("low_complexity")
    elif entry["complexity_label"] == "hard":
        reasons.append("high_complexity")
    return list(dict.fromkeys(reasons))


def build_folder_plan_payload(
    *,
    config: Config,
    source_dir: str | Path,
    inventory: HeaderInventoryReport,
    test_index: CCCLTestIndexReport,
    dep_graph: HeaderDependencyGraphReport,
    status_report: MigrationStatusReport,
    options: FolderPlanOptions | None = None,
) -> dict:
    """Build a deterministic folder migration plan payload."""
    options = options or FolderPlanOptions()
    header_root = Path(inventory.header_root)
    namespace = namespace_for_root(inventory.header_root)
    scope = folder_scope_relpath(source_dir, header_root=header_root)
    dep_by_header = {entry.header: list(entry.dependencies) for entry in dep_graph.graph}
    dep_entries = _dep_entry_map(dep_graph)
    status_by_header = {entry.source_header: entry for entry in status_report.headers}
    target_health_by_std_relpath = _target_header_health(status_report)
    candidate_by_header = {entry.source_header: entry for entry in status_report.batch_candidates}
    test_by_header = {mapping.header: list(mapping.tests) for mapping in test_index.mappings}
    test_kind_by_path = {entry.relative_path: entry.kind for entry in test_index.tests}
    order_index = {header: idx for idx, header in enumerate(dep_graph.topological_order)}
    cycles = _cycle_nodes(dep_graph)

    headers = [
        header.relative_path for header in inventory.headers
        if _in_scope(header.relative_path, scope)
    ]
    headers.sort(key=lambda h: (order_index.get(h, 10**9), h))
    if not headers:
        raise ValueError(
            f"source-dir {source_dir!r} resolved to {scope!r}, but no headers were found under {HEADER_ROOT_REL}"
        )

    analyses: list[dict] = []
    eligible: list[dict] = []
    blocked_or_deferred: list[dict] = []
    for header in headers:
        inv_entry = next(h for h in inventory.headers if h.relative_path == header)
        status_entry = status_by_header.get(header)
        candidate = candidate_by_header.get(header)
        dep_entry = dep_entries.get(header)
        deps = dep_by_header.get(header, [])
        closure_deps = _dependency_closure(header, dep_by_header)
        external_groups = _external_dependency_groups(
            closure=closure_deps,
            scope=scope,
            status_by_header=status_by_header,
            target_health_by_std_relpath=target_health_by_std_relpath,
            config=config,
        )
        external_approval_required = _external_approval_required(external_groups)
        external_satisfied_count = len(external_groups["external_satisfied_dependencies"])
        external_unverified_count = len(external_groups["external_unverified_dependencies"])
        external_missing_count = len(external_groups["external_missing_dependencies"])
        external_broken_count = len(external_groups["external_broken_dependencies"])
        policy_deferred_count = len(external_groups["policy_deferred_dependencies"])
        mapped_tests = test_by_header.get(header, [])
        kind_counts: dict[str, int] = {}
        for test in mapped_tests:
            kind = test_kind_by_path.get(test, "unknown")
            kind_counts[kind] = kind_counts.get(kind, 0) + 1
        stats = _source_stats(header_root, header)
        true_missing = candidate.true_missing_dependency_count if candidate else 0
        closure = candidate.dependency_closure_size if candidate else len(closure_deps)
        unknown_count = len(dep_entry.unknown_cuda_std_includes) if dep_entry else 0
        score = _complexity_score(
            stats=stats,
            direct_deps=len(deps),
            closure_size=closure,
            unknown_count=unknown_count,
            conditional_count=len(inv_entry.conditional_includes),
            true_missing_dependency_count=true_missing,
        )
        analysis = {
            "source_header": header,
            "include": f"{namespace}/{header}",
            "module": inv_entry.module,
            "shape": inv_entry.shape,
            "target_relpath": status_entry.target_relpath if status_entry else "",
            "status": status_entry.status if status_entry else "unknown",
            "target_exists": bool(status_entry.target_exists) if status_entry else False,
            "direct_dependencies": list(deps),
            "direct_dependency_count": len(deps),
            "dependency_closure": list(closure_deps),
            "include_dependencies": list(dep_entry.include_dependencies) if dep_entry else [],
            "symbol_dependencies": list(dep_entry.symbol_dependencies) if dep_entry else [],
            "symbol_dependency_includes": list(dep_entry.symbol_dependency_includes) if dep_entry else [],
            "symbol_dependency_symbols": list(dep_entry.symbol_dependency_symbols) if dep_entry else [],
            "symbol_dependency_count": len(dep_entry.symbol_dependencies) if dep_entry else 0,
            "in_scope_dependency_count": sum(1 for dep in deps if _in_scope(dep, scope)),
            "external_dependency_count": sum(1 for dep in deps if not _in_scope(dep, scope)),
            "external_dependency_closure": [dep for dep in closure_deps if not _in_scope(dep, scope)],
            "external_dependency_closure_count": sum(1 for dep in closure_deps if not _in_scope(dep, scope)),
            "external_satisfied_dependencies": external_groups["external_satisfied_dependencies"],
            "external_unverified_dependencies": external_groups["external_unverified_dependencies"],
            "external_missing_dependencies": external_groups["external_missing_dependencies"],
            "external_broken_dependencies": external_groups["external_broken_dependencies"],
            "policy_deferred_dependencies": external_groups["policy_deferred_dependencies"],
            "external_satisfied_dependency_count": external_satisfied_count,
            "external_unverified_dependency_count": external_unverified_count,
            "external_missing_dependency_count": external_missing_count,
            "external_broken_dependency_count": external_broken_count,
            "policy_deferred_dependency_count": policy_deferred_count,
            "external_dependency_approval_required": external_approval_required,
            "external_dependency_issue_count": (
                external_unverified_count
                + external_missing_count
                + external_broken_count
            ),
            "dependency_closure_size": closure,
            "unknown_cuda_std_includes": list(dep_entry.unknown_cuda_std_includes) if dep_entry else [],
            "conditional_includes": list(inv_entry.conditional_includes),
            "mapped_tests": mapped_tests,
            "mapped_test_count": len(mapped_tests),
            "test_kind_counts": kind_counts,
            "host_test_suitability": candidate.host_test_suitability if candidate else "unknown",
            "kernel_test_suitability": candidate.kernel_test_suitability if candidate else "unknown",
            "true_missing_dependency_count": true_missing,
            "candidate_score": candidate.score if candidate else 0,
            "rank_reasons": list(candidate.rank_reasons) if candidate else [],
            "complexity_score": score,
            "complexity_label": _complexity_label(score),
            "source_stats": stats,
            "in_cycle": header in cycles,
        }
        analysis["planning_reasons"] = _analysis_reason(analysis)
        analyses.append(analysis)

        is_eligible = (
            analysis["status"] == "pending"
            and not analysis["target_exists"]
            and candidate is not None
            and not analysis["in_cycle"]
            and not analysis["external_dependency_approval_required"]
        )
        if is_eligible:
            eligible.append(analysis)
        else:
            blocked_or_deferred.append({
                "source_header": header,
                "reason": analysis["planning_reasons"] or ["not_a_batch_candidate"],
            })

    eligible.sort(
        key=lambda item: (
            item["true_missing_dependency_count"],
            0 if item["mapped_test_count"] else 1,
            item["complexity_score"],
            item["dependency_closure_size"],
            -item["candidate_score"],
            order_index.get(item["source_header"], 10**9),
            item["source_header"],
        )
    )
    first = eligible[: max(1, options.first_batch_size)]
    first_headers = [item["source_header"] for item in first]
    rest_headers = [item["source_header"] for item in eligible if item["source_header"] not in set(first_headers)]
    followups = [
        {
            "name": f"followup-{idx}",
            "headers": headers,
            "rationale": "按依赖叶子优先序继续推进；执行前可再次 folder-plan 刷新状态。",
        }
        for idx, headers in enumerate(_chunk(rest_headers, options.followup_batch_size), start=1)
    ]

    return {
        "schema_version": 1,
        "approved": False,
        "source_dir": str(source_dir),
        "scope_relpath": scope,
        "cccl_repo": inventory.cccl_repo,
        "header_root": inventory.header_root,
        "target_repo": config.target_repo,
        "summary": {
            "header_count": len(headers),
            "eligible_candidate_count": len(eligible),
            "blocked_or_deferred_count": len(blocked_or_deferred),
            "cycle_count": len([cycle for cycle in dep_graph.cycles if any(_in_scope(h, scope) for h in cycle)]),
            "independent_leaf_candidate_count": sum(
                1 for item in analyses
                if item["status"] == "pending"
                and not item["target_exists"]
                and item["dependency_closure_size"] == 0
            ),
            "external_dependency_decision_count": sum(
                1 for item in analyses if item["external_dependency_approval_required"]
            ),
            "external_missing_dependency_count": len({
                dep["dependency"]
                for item in analyses
                for dep in item["external_missing_dependencies"]
            }),
            "external_unverified_dependency_count": len({
                dep["dependency"]
                for item in analyses
                for dep in item["external_unverified_dependencies"]
            }),
            "external_broken_dependency_count": len({
                dep["dependency"]
                for item in analyses
                for dep in item["external_broken_dependencies"]
            }),
        },
        "recommended_first_batch": [
            {
                "source_header": item["source_header"],
                "complexity_label": item["complexity_label"],
                "complexity_score": item["complexity_score"],
                "rationale": item["planning_reasons"],
            }
            for item in first
        ],
        "followup_batches": followups,
        "blocked_or_deferred": blocked_or_deferred,
        "independent_leaf_candidates": [
            {
                "source_header": item["source_header"],
                "complexity_label": item["complexity_label"],
                "complexity_score": item["complexity_score"],
                "mapped_test_count": item["mapped_test_count"],
            }
            for item in analyses
            if item["status"] == "pending"
            and not item["target_exists"]
            and item["dependency_closure_size"] == 0
        ],
        "external_dependency_decisions": [
            {
                "source_header": item["source_header"],
                "external_missing_dependencies": item["external_missing_dependencies"],
                "external_unverified_dependencies": item["external_unverified_dependencies"],
                "external_broken_dependencies": item["external_broken_dependencies"],
                "policy_deferred_dependencies": item["policy_deferred_dependencies"],
            }
            for item in analyses
            if item["external_dependency_approval_required"]
        ],
        "headers": analyses,
        "model_recommendation": None,
    }


def _ai_candidate_view(plan: dict, max_items: int) -> list[dict]:
    candidates = [
        item for item in plan["headers"]
        if item["status"] == "pending" and not item["target_exists"] and not item["in_cycle"]
        and not item.get("external_dependency_approval_required")
    ]
    candidates.sort(key=lambda item: (item["complexity_score"], item["dependency_closure_size"], item["source_header"]))
    return candidates[: max(1, max_items)]


def _sanitize_ai_plan(raw: dict, base_plan: dict) -> dict:
    valid = {item["source_header"] for item in base_plan["headers"]}
    eligible = {
        item["source_header"] for item in base_plan["headers"]
        if item["status"] == "pending" and not item["target_exists"] and not item["in_cycle"]
        and not item.get("external_dependency_approval_required")
    }

    def valid_headers(seq) -> list[str]:
        out: list[str] = []
        for item in seq or []:
            header = item.get("source_header") if isinstance(item, dict) else item
            if header in valid and header in eligible and header not in out:
                out.append(header)
        return out

    first = valid_headers(raw.get("first_batch"))
    followups: list[dict] = []
    used = set(first)
    for idx, batch in enumerate(raw.get("followup_batches") or [], start=1):
        if not isinstance(batch, dict):
            continue
        headers = [h for h in valid_headers(batch.get("headers")) if h not in used]
        if not headers:
            continue
        used.update(headers)
        followups.append({
            "name": str(batch.get("name") or f"followup-{idx}"),
            "headers": headers,
            "rationale": str(batch.get("rationale") or batch.get("reason") or ""),
        })
    return {
        "summary": str(raw.get("summary") or ""),
        "first_batch": first,
        "followup_batches": followups,
        "risk_notes": [str(x) for x in raw.get("risk_notes") or []],
        "raw": raw,
    }


def refine_folder_plan_with_model(
    *,
    plan: dict,
    model_client: BaseModelClient,
    options: FolderPlanOptions,
    show_model_io: bool = False,
) -> dict:
    """Ask the model to recommend batches from bounded, factual folder metadata."""
    system_prompt = (
        "你是 ASC-STL 迁移规划智能体。只能基于用户提供的 JSON 元数据推荐迁移批次；"
        "不要编造不存在的 header。输出必须是 JSON 对象。"
    )
    payload = {
        "task": "从文件夹候选中推荐首批迁移清单和后续迁移批次",
        "rules": [
            "首批优先低复杂度、依赖闭包小、true_missing_dependency_count 低、有测试映射的 header。",
            "同一个 header 不要重复出现在多个批次。",
            "不要推荐 status 非 pending、target_exists=true、in_cycle=true 的 header。",
            "不要推荐 external_dependency_approval_required=true 的 header；这些需要用户先批准跨包依赖。",
            "只输出 JSON：summary, first_batch, followup_batches, risk_notes。",
        ],
        "folder_summary": plan["summary"],
        "scope_relpath": plan["scope_relpath"],
        "candidates": _ai_candidate_view(plan, options.max_ai_candidates),
    }
    user_content = json.dumps(payload, ensure_ascii=False, indent=2)
    if show_model_io:
        print("\n=== folder-plan model request ===")
        print(user_content)
    raw = model_client.generate(system_prompt=system_prompt, user_content=user_content)
    data = extract_json_object(raw)
    recommendation = _sanitize_ai_plan(data, plan)
    if recommendation["first_batch"]:
        by_header = {item["source_header"]: item for item in plan["headers"]}
        plan["recommended_first_batch"] = [
            {
                "source_header": header,
                "complexity_label": by_header[header]["complexity_label"],
                "complexity_score": by_header[header]["complexity_score"],
                "rationale": by_header[header]["planning_reasons"],
            }
            for header in recommendation["first_batch"]
        ]
    if recommendation["followup_batches"]:
        plan["followup_batches"] = recommendation["followup_batches"]
    plan["model_recommendation"] = recommendation
    return plan


def _dependency_counter(plan: dict, key: str) -> Counter:
    counts: Counter = Counter()
    for item in plan.get("headers") or []:
        for dep in item.get(key) or []:
            name = dep.get("dependency") if isinstance(dep, dict) else dep
            if name:
                counts[str(name)] += 1
    return counts


def _format_top_dependencies(counter: Counter, *, limit: int = MARKDOWN_TOP_DEPENDENCIES) -> str:
    if not counter:
        return "none"
    parts = [f"`{dep}` x{count}" for dep, count in counter.most_common(limit)]
    remaining = len(counter) - len(parts)
    if remaining > 0:
        parts.append(f"... +{remaining} more")
    return ", ".join(parts)


def _dependency_names(seq: list, *, limit: int = 6) -> tuple[list[str], int]:
    names = [
        str(item.get("dependency") if isinstance(item, dict) else item)
        for item in (seq or [])
        if (item.get("dependency") if isinstance(item, dict) else item)
    ]
    return names[:limit], max(0, len(names) - limit)


def _format_dependency_preview(seq: list, *, limit: int = 6) -> str:
    names, remaining = _dependency_names(seq, limit=limit)
    if not names:
        return ""
    text = ", ".join(f"`{name}`" for name in names)
    if remaining:
        text += f", ... +{remaining} more"
    return text


def _details_json_name(json_name: str) -> str:
    name = Path(json_name)
    if name.name == DEFAULT_FOLDER_PLAN_JSON:
        return DEFAULT_FOLDER_PLAN_DETAILS_JSON
    suffix = name.suffix or ".json"
    return f"{name.stem}_details{suffix}"


def _preview_dependencies(items: list, *, limit: int = JSON_DEPENDENCY_PREVIEW_LIMIT) -> list:
    return copy.deepcopy((items or [])[:limit])


def _slim_header_entry(item: dict) -> dict:
    out = copy.deepcopy(item)
    out.pop("dependency_closure", None)
    out.pop("external_dependency_closure", None)
    for key in (
        "external_satisfied_dependencies",
        "external_unverified_dependencies",
        "external_missing_dependencies",
        "external_broken_dependencies",
        "policy_deferred_dependencies",
    ):
        deps = item.get(key) or []
        out[key] = _preview_dependencies(deps)
        if len(deps) > JSON_DEPENDENCY_PREVIEW_LIMIT:
            out[f"{key}_truncated"] = len(deps) - JSON_DEPENDENCY_PREVIEW_LIMIT
    return out


def _slim_external_decision(item: dict) -> dict:
    out = {"source_header": item.get("source_header", "")}
    for key in (
        "external_missing_dependencies",
        "external_unverified_dependencies",
        "external_broken_dependencies",
        "policy_deferred_dependencies",
    ):
        deps = item.get(key) or []
        out[key] = _preview_dependencies(deps)
        out[f"{key}_count"] = len(deps)
        if len(deps) > JSON_DEPENDENCY_PREVIEW_LIMIT:
            out[f"{key}_truncated"] = len(deps) - JSON_DEPENDENCY_PREVIEW_LIMIT
    return out


def _slim_folder_plan(plan: dict, *, details_json_name: str) -> dict:
    out = copy.deepcopy(plan)
    out["details_json"] = details_json_name
    out["headers"] = [_slim_header_entry(item) for item in plan.get("headers") or []]
    out["external_dependency_decisions"] = [
        _slim_external_decision(item)
        for item in plan.get("external_dependency_decisions") or []
    ]
    if isinstance(out.get("model_recommendation"), dict):
        out["model_recommendation"].pop("raw", None)
    return out


def plan_to_markdown(
    plan: dict,
    *,
    json_name: str = DEFAULT_FOLDER_PLAN_JSON,
    details_json_name: str | None = None,
) -> str:
    lines: list[str] = []
    details_json_name = details_json_name or _details_json_name(json_name)
    lines.append(f"# Folder Migration Plan: `{plan['scope_relpath'] or '.'}`")
    lines.append("")
    lines.append(f"- approved: `{plan.get('approved', False)}`")
    lines.append(f"- cccl_repo: `{plan['cccl_repo']}`")
    lines.append(f"- target_repo: `{plan['target_repo']}`")
    lines.append(f"- execution_json: `outputs/{json_name}`")
    lines.append(f"- detail_json: `outputs/{details_json_name}`")
    summary = plan["summary"]
    lines.append(
        f"- headers: {summary['header_count']}, eligible: {summary['eligible_candidate_count']}, "
        f"blocked/deferred: {summary['blocked_or_deferred_count']}, cycles: {summary['cycle_count']}"
    )
    lines.append(
        f"- independent_leaf_candidates: {summary.get('independent_leaf_candidate_count', 0)}, "
        f"external_dependency_decisions: {summary.get('external_dependency_decision_count', 0)}"
    )
    lines.append(
        f"- external missing/unverified/broken: "
        f"{summary.get('external_missing_dependency_count', 0)}/"
        f"{summary.get('external_unverified_dependency_count', 0)}/"
        f"{summary.get('external_broken_dependency_count', 0)}"
    )
    if plan.get("model_recommendation"):
        lines.append(f"- model_summary: {plan['model_recommendation'].get('summary', '')}")
    lines.append("")
    lines.append("## Recommended First Batch")
    for idx, item in enumerate(plan.get("recommended_first_batch") or [], start=1):
        reasons = ", ".join(item.get("rationale") or [])
        lines.append(
            f"{idx}. `{item['source_header']}` "
            f"({item['complexity_label']}, score={item['complexity_score']}) - {reasons}"
        )
    lines.append("")
    lines.append("## Follow-Up Batches")
    for batch in plan.get("followup_batches") or []:
        lines.append(f"- {batch['name']}: {', '.join(f'`{h}`' for h in batch.get('headers', []))}")
        if batch.get("rationale"):
            lines.append(f"  {batch['rationale']}")
    lines.append("")
    lines.append("## Independent Leaf Candidates")
    for item in plan.get("independent_leaf_candidates") or []:
        lines.append(
            f"- `{item['source_header']}` "
            f"({item['complexity_label']}, score={item['complexity_score']}, tests={item['mapped_test_count']})"
        )
    lines.append("")
    lines.append("## External Dependency Decisions")
    decisions = plan.get("external_dependency_decisions") or []
    lines.append(f"- headers_needing_decision: {len(decisions)}")
    lines.append(
        "- top_missing: "
        + _format_top_dependencies(_dependency_counter(plan, "external_missing_dependencies"))
    )
    lines.append(
        "- top_unverified: "
        + _format_top_dependencies(_dependency_counter(plan, "external_unverified_dependencies"))
    )
    lines.append(
        "- top_broken: "
        + _format_top_dependencies(_dependency_counter(plan, "external_broken_dependencies"))
    )
    lines.append(
        "- top_policy_deferred: "
        + _format_top_dependencies(_dependency_counter(plan, "policy_deferred_dependencies"))
    )
    if decisions:
        lines.append("")
        lines.append("### Header Samples")
    for item in decisions[:MARKDOWN_HEADER_SAMPLES]:
        parts = []
        missing = _format_dependency_preview(item.get("external_missing_dependencies") or [])
        unverified = _format_dependency_preview(item.get("external_unverified_dependencies") or [])
        broken = _format_dependency_preview(item.get("external_broken_dependencies") or [])
        if missing:
            parts.append("missing=" + missing)
        if unverified:
            parts.append("unverified=" + unverified)
        if broken:
            parts.append("broken=" + broken)
        lines.append(f"- `{item['source_header']}`: {'; '.join(parts)}")
    if len(decisions) > MARKDOWN_HEADER_SAMPLES:
        lines.append(f"- ... +{len(decisions) - MARKDOWN_HEADER_SAMPLES} more headers; see detail JSON.")
    lines.append("")
    lines.append("## Blocked Or Deferred")
    for item in plan.get("blocked_or_deferred") or []:
        lines.append(f"- `{item['source_header']}`: {', '.join(item.get('reason') or [])}")
    lines.append("")
    lines.append("## How To Run After Review")
    lines.append("```bash")
    lines.append(f"python3 main.py folder-migrate --plan outputs/{json_name} --batch first --approve --real-ai --with-tests")
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def write_folder_plan(plan: dict, output_dir: str | Path, *, json_name: str = DEFAULT_FOLDER_PLAN_JSON,
                      md_name: str = DEFAULT_FOLDER_PLAN_MD) -> tuple[Path, Path]:
    out = Path(output_dir)
    json_path = out / json_name
    md_path = out / md_name
    details_name = _details_json_name(json_name)
    details_path = out / details_name
    detail_plan = copy.deepcopy(plan)
    detail_plan["details_json"] = details_name
    save_text(details_path, json.dumps(detail_plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    save_text(json_path, json.dumps(_slim_folder_plan(plan, details_json_name=details_name),
                                    ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    save_text(md_path, plan_to_markdown(plan, json_name=json_name, details_json_name=details_name) + "\n")
    return json_path, md_path
