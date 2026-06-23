"""Bounded AI migration context pack generation.

The context pack is intentionally structured and deterministic. It collects
just enough local evidence for an entry CCCL header migration without dumping
large unrelated repository content into prompts.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Mapping, Sequence

from core.analysis.dep_graph import HeaderDependencyGraphReport
from core.analysis.inventory import (
    HEADER_ROOT_REL,
    HeaderInventoryReport,
    namespace_for_root,
)
from core.analysis.migration_status import (
    MigrationStatusReport,
)
from core.analysis.test_index import CCCLTestIndexReport
from core.common.utils import save_text
from core.knowledge.example_retrieval import (
    _name_from_relpath,
    _score,
    _tokens,
    discover_header_pairs,
    discover_test_triples,
)

DEFAULT_CONTEXT_PACK_REPORT_PREFIX = "migration_context"

DEFAULT_LIMITS = {
    "max_source_chars": 16000,
    "max_accl_chars": 16000,
    "max_sibling_chars": 6000,
    "max_test_chars": 8000,
    "max_example_chars": 8000,
    "max_siblings": 4,
    "max_tests": 5,
    "max_examples": 3,
}

_VALIDATED_EXAMPLE_STATUSES = {"host_passed", "kernel_passed", "full_passed"}


def _safe_name(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value)
    safe = safe.strip("._")
    return safe or "header"


def default_context_pack_filename(entry_header: str) -> str:
    stem = _safe_name(entry_header.replace("/", "__"))
    return f"{DEFAULT_CONTEXT_PACK_REPORT_PREFIX}_{stem}.json"


def _is_env_path(path: Path) -> bool:
    return any(part == ".env" or part.startswith(".env.") for part in path.parts)


def _resolve_under(path: str | Path, root: str | Path) -> Path:
    resolved = Path(path).resolve()
    root_resolved = Path(root).resolve()
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError(f"path is outside allowed root: {resolved}") from exc
    if _is_env_path(resolved):
        raise ValueError(f"refusing to read .env path: {resolved}")
    return resolved


def _read_bounded(path: str | Path, *, root: str | Path, max_chars: int) -> dict:
    resolved = _resolve_under(path, root)
    if not resolved.exists():
        return {
            "exists": False,
            "path": str(resolved),
            "text": "",
            "truncated": False,
            "char_count": 0,
        }
    if not resolved.is_file():
        raise ValueError(f"path is not a file: {resolved}")
    text = resolved.read_text(encoding="utf-8", errors="replace")
    truncated = len(text) > max_chars
    return {
        "exists": True,
        "path": str(resolved),
        "text": text[:max_chars],
        "truncated": truncated,
        "char_count": len(text),
    }


def _by_header_status(report: MigrationStatusReport) -> dict[str, dict]:
    return {entry.source_header: entry.to_dict() for entry in report.headers}


def _by_test_path(test_index: CCCLTestIndexReport) -> dict[str, dict]:
    return {entry.relative_path: entry.to_dict() for entry in test_index.tests}


def _dep_map(dep_graph: HeaderDependencyGraphReport) -> dict[str, list[str]]:
    return {entry.header: list(entry.dependencies) for entry in dep_graph.graph}


def _closure_leaf_first(entry_header: str, dep_graph: HeaderDependencyGraphReport) -> list[str]:
    dep_map = _dep_map(dep_graph)
    reachable: set[str] = set()

    def visit(node: str) -> None:
        for dep in dep_map.get(node, []):
            if dep in reachable:
                continue
            reachable.add(dep)
            visit(dep)

    visit(entry_header)
    order_index = {header: idx for idx, header in enumerate(dep_graph.topological_order)}
    return sorted(reachable, key=lambda header: (order_index.get(header, 10**9), header))


def _dependency_nodes(
    *,
    entry_header: str,
    closure: list[str],
    status_by_header: dict[str, dict],
    dep_graph: HeaderDependencyGraphReport,
) -> list[dict]:
    dep_map = _dep_map(dep_graph)
    nodes: list[dict] = []
    for header in closure:
        status = status_by_header.get(header, {})
        nodes.append(
            {
                "source_header": header,
                "dependencies": dep_map.get(header, []),
                "status": status.get("status"),
                "target_exists": status.get("target_exists", False),
                "target_relpath": status.get("target_relpath"),
                "missing_dependencies": status.get("missing_dependencies", []),
            }
        )
    return nodes


def _existing_counterpart(
    *,
    entry_status: dict,
    target_repo: str | Path,
    max_chars: int,
) -> dict:
    target_relpath = entry_status["target_relpath"]
    path = Path(target_repo) / target_relpath
    content = _read_bounded(path, root=target_repo, max_chars=max_chars)
    return {
        "target_relpath": target_relpath,
        "exists": content["exists"],
        "content": content,
    }


def _nearby_siblings(
    *,
    entry_status: dict,
    target_repo: str | Path,
    max_siblings: int,
    max_chars: int,
) -> list[dict]:
    target_relpath = entry_status["target_relpath"]
    target_path = Path(target_repo) / target_relpath
    sibling_dir = target_path.parent
    if not sibling_dir.is_dir():
        return []
    root = Path(target_repo)
    siblings: list[dict] = []
    for path in sorted(p for p in sibling_dir.iterdir() if p.is_file()):
        relpath = path.relative_to(root).as_posix()
        if relpath == target_relpath:
            continue
        siblings.append(
            {
                "target_relpath": relpath,
                "content": _read_bounded(path, root=target_repo, max_chars=max_chars),
            }
        )
        if len(siblings) >= max_siblings:
            break
    return siblings


def _mapped_tests(
    *,
    entry_status: dict,
    test_index: CCCLTestIndexReport,
    max_tests: int,
    max_chars: int,
) -> list[dict]:
    test_by_path = _by_test_path(test_index)
    tests: list[dict] = []
    for relpath in entry_status.get("mapped_tests", [])[:max_tests]:
        metadata = test_by_path.get(relpath)
        if metadata is None:
            continue
        path = Path(test_index.test_root) / relpath
        tests.append(
            {
                "relative_path": relpath,
                "metadata": metadata,
                "content": _read_bounded(path, root=test_index.test_root, max_chars=max_chars),
            }
        )
    return tests


def _header_for_example_name(name: str, status_by_header: dict[str, dict]) -> dict | None:
    matches = []
    for header, status in status_by_header.items():
        if Path(header).stem == name:
            matches.append((header.count("/"), header, status))
    if not matches:
        return None
    _, header, status = sorted(matches)[0]
    return {"source_header": header, "status": status}


def _rank_example_pairs(
    *,
    pairs: list[dict],
    query_name: str,
    query_text: str,
    text_key: str,
) -> list[dict]:
    query_tokens = _tokens(query_text)
    scored = []
    for idx, candidate in enumerate(pairs):
        try:
            candidate_text = Path(candidate[text_key]).read_text(encoding="utf-8", errors="replace")
        except OSError:
            candidate_text = ""
        score = _score(
            query_name,
            query_tokens,
            candidate.get("name", ""),
            _tokens(candidate_text),
        )
        scored.append((score, -idx, candidate))
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [candidate for _, _, candidate in scored]


def _validated_examples(
    *,
    entry_header: str,
    source_text: str,
    examples_root: str | Path,
    status_by_header: dict[str, dict],
    max_examples: int,
    max_chars: int,
) -> list[dict]:
    root = Path(examples_root)
    header_dir = root / "headers"
    test_dir = root / "tests"
    query_name = _name_from_relpath(entry_header)

    header_pairs = _rank_example_pairs(
        pairs=discover_header_pairs(header_dir),
        query_name=query_name,
        query_text=source_text,
        text_key="cccl",
    )
    test_triples = {triple["name"]: triple for triple in discover_test_triples(test_dir)}

    examples: list[dict] = []
    for pair in header_pairs:
        name = pair["name"]
        if name == query_name:
            continue
        evidence = _header_for_example_name(name, status_by_header)
        if not evidence:
            continue
        status = evidence["status"].get("status")
        if status not in _VALIDATED_EXAMPLE_STATUSES:
            continue
        item = {
            "name": name,
            "source_header": evidence["source_header"],
            "status": status,
            "header_example": {
                "cccl": _read_bounded(pair["cccl"], root=root, max_chars=max_chars),
                "accl": _read_bounded(pair["accl"], root=root, max_chars=max_chars),
            },
        }
        triple = test_triples.get(name)
        if triple:
            item["test_example"] = {
                "cccl_test": _read_bounded(triple["cccl_test"], root=root, max_chars=max_chars),
                "accl_host": _read_bounded(triple["accl_host"], root=root, max_chars=max_chars),
                "accl_kernel_spec": _read_bounded(
                    triple["accl_kernel_spec"],
                    root=root,
                    max_chars=max_chars,
                ),
            }
        examples.append(item)
        if len(examples) >= max_examples:
            break
    return examples


def _ledger_evidence(entry_status: dict, status_report: MigrationStatusReport) -> list[dict]:
    keys = {
        entry_status["source_header"],
        entry_status["target_relpath"],
    }
    return [
        entry.to_dict()
        for entry in status_report.ledger_entries
        if entry.key in keys
    ]


def _missing_dependency_evidence(
    *,
    entry_header: str,
    closure: list[str],
    status_report: MigrationStatusReport,
) -> list[dict]:
    headers = {entry_header, *closure}
    return [
        entry.to_dict()
        for entry in status_report.missing_dependencies
        if entry.header in headers
    ]


def _batch_candidate_evidence(
    entry_header: str,
    status_report: MigrationStatusReport,
) -> dict | None:
    for candidate in status_report.batch_candidates:
        if candidate.source_header == entry_header:
            return candidate.to_dict()
    return None


def build_migration_context_pack(
    *,
    entry_header: str,
    inventory: HeaderInventoryReport,
    test_index: CCCLTestIndexReport,
    dep_graph: HeaderDependencyGraphReport,
    status_report: MigrationStatusReport,
    target_repo: str | Path,
    examples_root: str | Path,
    limits: dict | None = None,
) -> dict:
    """Build a deterministic bounded context pack for one CCCL header."""
    effective_limits = dict(DEFAULT_LIMITS)
    if limits:
        effective_limits.update(limits)

    header_by_relpath = {header.relative_path: header for header in inventory.headers}
    if entry_header not in header_by_relpath:
        raise ValueError(f"entry header not found in inventory: {entry_header}")

    status_by_header = _by_header_status(status_report)
    if entry_header not in status_by_header:
        raise ValueError(f"entry header not found in migration status: {entry_header}")

    source_path = Path(inventory.header_root) / entry_header
    source_content = _read_bounded(
        source_path,
        root=inventory.header_root,
        max_chars=effective_limits["max_source_chars"],
    )
    source_text = source_content["text"]
    entry_status = status_by_header[entry_header]
    closure = _closure_leaf_first(entry_header, dep_graph)
    namespace = namespace_for_root(inventory.header_root)

    return {
        "schema_version": 1,
        "entry_header": entry_header,
        "include": f"{namespace}/{entry_header}",
        "source_header": {
            "metadata": header_by_relpath[entry_header].to_dict(),
            "content": source_content,
        },
        "dependency_closure": {
            "direct_dependencies": list(_dep_map(dep_graph).get(entry_header, [])),
            "leaf_first": list(closure),
            "closure_size": len(closure),
            "cycles_touching_entry": [
                list(cycle)
                for cycle in dep_graph.cycles
                if entry_header in cycle
            ],
            "nodes": _dependency_nodes(
                entry_header=entry_header,
                closure=closure,
                status_by_header=status_by_header,
                dep_graph=dep_graph,
            ),
            "missing_dependency_evidence": _missing_dependency_evidence(
                entry_header=entry_header,
                closure=closure,
                status_report=status_report,
            ),
        },
        "existing_accl_counterpart": _existing_counterpart(
            entry_status=entry_status,
            target_repo=target_repo,
            max_chars=effective_limits["max_accl_chars"],
        ),
        "nearby_accl_sibling_headers": _nearby_siblings(
            entry_status=entry_status,
            target_repo=target_repo,
            max_siblings=effective_limits["max_siblings"],
            max_chars=effective_limits["max_sibling_chars"],
        ),
        "mapped_upstream_tests": _mapped_tests(
            entry_status=entry_status,
            test_index=test_index,
            max_tests=effective_limits["max_tests"],
            max_chars=effective_limits["max_test_chars"],
        ),
        "relevant_validated_examples": _validated_examples(
            entry_header=entry_header,
            source_text=source_text,
            examples_root=examples_root,
            status_by_header=status_by_header,
            max_examples=effective_limits["max_examples"],
            max_chars=effective_limits["max_example_chars"],
        ),
        "ledger_status_evidence": {
            "entry_status": entry_status,
            "ledger_entries": _ledger_evidence(entry_status, status_report),
            "batch_candidate": _batch_candidate_evidence(entry_header, status_report),
        },
        "bounds": {
            "limits": effective_limits,
            "source_root": inventory.header_root,
            "test_root": test_index.test_root,
            "target_repo": str(Path(target_repo).resolve()),
            "examples_root": str(Path(examples_root).resolve()),
        },
    }


def build_migration_context_pack_from_scans(
    *,
    entry_header: str,
    cccl_repo: str | Path | None,
    target_repo: str | Path,
    examples_root: str | Path,
    ledger_path: str | Path | None,
    target_repo_prefix: str,
    segment_substitutions: list[dict] | None = None,
    symbol_dependency_rules: Sequence[Mapping] | None = None,
    limits: dict | None = None,
    state_status_map: dict[str, str] | None = None,
    include_root_rel: str | Path = HEADER_ROOT_REL,
    test_root_rel: str | Path | None = None,
) -> dict:
    from core.analysis.dep_graph import scan_dependency_graph
    from core.analysis.inventory import scan_header_inventory
    from core.analysis.migration_status import build_migration_status_report
    from core.analysis.test_index import TEST_ROOT_REL, scan_test_index

    test_root_rel = test_root_rel if test_root_rel is not None else TEST_ROOT_REL
    inventory = scan_header_inventory(
        cccl_repo, include_root_rel=include_root_rel, symbol_dependency_rules=symbol_dependency_rules
    )
    test_index = scan_test_index(cccl_repo, include_root_rel=include_root_rel, test_root_rel=test_root_rel)
    dep_graph = scan_dependency_graph(
        cccl_repo, include_root_rel=include_root_rel, symbol_dependency_rules=symbol_dependency_rules
    )
    status_report = build_migration_status_report(
        inventory=inventory,
        test_index=test_index,
        dep_graph=dep_graph,
        target_repo=target_repo,
        ledger_path=ledger_path,
        target_repo_prefix=target_repo_prefix,
        segment_substitutions=segment_substitutions,
        state_status_map=state_status_map,
    )
    return build_migration_context_pack(
        entry_header=entry_header,
        inventory=inventory,
        test_index=test_index,
        dep_graph=dep_graph,
        status_report=status_report,
        target_repo=target_repo,
        examples_root=examples_root,
        limits=limits,
    )


def write_migration_context_pack(
    pack: dict,
    output_dir: str | Path,
    *,
    filename: str | None = None,
) -> Path:
    name = Path(filename or default_context_pack_filename(pack["entry_header"]))
    if name.is_absolute() or len(name.parts) != 1:
        raise ValueError("migration context pack filename must be a file name under outputs/")
    path = Path(output_dir) / name
    payload = json.dumps(pack, ensure_ascii=False, indent=2, sort_keys=True)
    save_text(path, payload + "\n")
    return path
