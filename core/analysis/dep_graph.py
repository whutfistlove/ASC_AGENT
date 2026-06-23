"""Deterministic CCCL header dependency graph support."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from core.analysis.inventory import (
    DEFAULT_INCLUDE_NAMESPACE,
    HEADER_ROOT_REL,
    HeaderInventoryReport,
    include_to_header_relpath,
    namespace_for_root,
    scan_header_inventory,
)
from core.common.utils import save_text

DEFAULT_DEP_GRAPH_REPORT_NAME = "cccl_dep_graph.json"


@dataclass(frozen=True)
class HeaderDependencyEntry:
    header: str
    include: str
    dependencies: list[str]
    dependency_includes: list[str]
    unknown_cuda_std_includes: list[str]
    include_dependencies: list[str]
    symbol_dependencies: list[str]
    symbol_dependency_includes: list[str]
    symbol_dependency_symbols: list[str]
    unknown_symbol_dependency_includes: list[str]

    def to_dict(self) -> dict:
        return {
            "dependencies": list(self.dependencies),
            "dependency_includes": list(self.dependency_includes),
            "header": self.header,
            "include_dependencies": list(self.include_dependencies),
            "include": self.include,
            "symbol_dependencies": list(self.symbol_dependencies),
            "symbol_dependency_includes": list(self.symbol_dependency_includes),
            "symbol_dependency_symbols": list(self.symbol_dependency_symbols),
            "unknown_cuda_std_includes": list(self.unknown_cuda_std_includes),
            "unknown_symbol_dependency_includes": list(self.unknown_symbol_dependency_includes),
        }


@dataclass(frozen=True)
class HeaderDependencyGraphReport:
    cccl_repo: str
    header_root: str
    graph: list[HeaderDependencyEntry]
    topological_order: list[str]
    cycles: list[list[str]]

    def summary(self) -> dict:
        edge_count = sum(len(entry.dependencies) for entry in self.graph)
        unknown_count = sum(len(entry.unknown_cuda_std_includes) for entry in self.graph)
        symbol_edge_count = sum(len(entry.symbol_dependencies) for entry in self.graph)
        unknown_symbol_count = sum(len(entry.unknown_symbol_dependency_includes) for entry in self.graph)
        return {
            "cycle_count": len(self.cycles),
            "edge_count": edge_count,
            "has_cycles": bool(self.cycles),
            "header_count": len(self.graph),
            "symbol_dependency_edge_count": symbol_edge_count,
            "topological_order_count": len(self.topological_order),
            "unknown_cuda_std_include_count": unknown_count,
            "unknown_symbol_dependency_count": unknown_symbol_count,
        }

    def to_dict(self) -> dict:
        return {
            "cccl_repo": self.cccl_repo,
            "cycles": [list(cycle) for cycle in self.cycles],
            "graph": [entry.to_dict() for entry in self.graph],
            "header_root": self.header_root,
            "summary": self.summary(),
            "topological_order": list(self.topological_order),
        }


def _resolve_dependency_includes(
    includes: list[str], known_headers: set[str], namespace: str = DEFAULT_INCLUDE_NAMESPACE
) -> tuple[set[str], set[str]]:
    dependencies: set[str] = set()
    unknown: set[str] = set()
    for include_path in includes:
        relpath = include_to_header_relpath(include_path, namespace)
        if relpath is None:
            continue
        if relpath in known_headers:
            dependencies.add(relpath)
        else:
            unknown.add(include_path)
    return dependencies, unknown


def _dependency_entry(header, known_headers: set[str], namespace: str = DEFAULT_INCLUDE_NAMESPACE) -> HeaderDependencyEntry:
    ns = namespace.strip("/")
    include_deps, include_unknown = _resolve_dependency_includes(list(header.includes), known_headers, namespace)
    symbol_deps, symbol_unknown = _resolve_dependency_includes(list(header.symbol_dependencies), known_headers, namespace)
    deps = sorted(include_deps | symbol_deps)
    symbol_dep_list = sorted(symbol_deps)
    return HeaderDependencyEntry(
        header=header.relative_path,
        include=f"{ns}/{header.relative_path}",
        dependencies=deps,
        dependency_includes=[f"{ns}/{dep}" for dep in deps],
        unknown_cuda_std_includes=sorted(include_unknown),
        include_dependencies=sorted(include_deps),
        symbol_dependencies=symbol_dep_list,
        symbol_dependency_includes=[f"{ns}/{dep}" for dep in symbol_dep_list],
        symbol_dependency_symbols=sorted({hit.symbol for hit in header.symbol_dependency_hits}),
        unknown_symbol_dependency_includes=sorted(symbol_unknown),
    )


def _canonical_cycle(stack: list[str], repeated: str) -> list[str]:
    """Return a stable representation of one DFS back-edge cycle."""
    try:
        start = stack.index(repeated)
    except ValueError:
        return [repeated, repeated]
    cycle = stack[start:] + [repeated]
    body = cycle[:-1]
    if not body:
        return cycle
    rotations = [body[i:] + body[:i] for i in range(len(body))]
    best = min(rotations)
    return best + [best[0]]


def _leaf_first_topological_order(graph: dict[str, list[str]]) -> tuple[list[str], list[list[str]]]:
    permanent: set[str] = set()
    temporary: set[str] = set()
    order: list[str] = []
    cycles: list[list[str]] = []
    seen_cycles: set[tuple[str, ...]] = set()

    def visit(node: str, stack: list[str]) -> None:
        if node in permanent:
            return
        if node in temporary:
            cycle = _canonical_cycle(stack, node)
            key = tuple(cycle)
            if key not in seen_cycles:
                seen_cycles.add(key)
                cycles.append(cycle)
            return

        temporary.add(node)
        stack.append(node)
        for dep in graph.get(node, []):
            visit(dep, stack)
        stack.pop()
        temporary.remove(node)
        permanent.add(node)
        order.append(node)

    for node in sorted(graph):
        visit(node, [])

    return order, sorted(cycles)


def build_dependency_graph_report(inventory: HeaderInventoryReport) -> HeaderDependencyGraphReport:
    """Build a header dependency graph from a header inventory report.

    The include namespace (`cuda/std` vs `cuda`) is derived from the inventory's
    header root, so std and the cuda extension layer both produce correct edges.
    """
    namespace = namespace_for_root(inventory.header_root)
    known_headers = {header.relative_path for header in inventory.headers}
    entries = [
        _dependency_entry(header, known_headers, namespace)
        for header in inventory.headers
    ]
    entries = sorted(entries, key=lambda entry: entry.header)
    graph = {entry.header: entry.dependencies for entry in entries}
    order, cycles = _leaf_first_topological_order(graph)
    return HeaderDependencyGraphReport(
        cccl_repo=inventory.cccl_repo,
        header_root=inventory.header_root,
        graph=entries,
        topological_order=order,
        cycles=cycles,
    )


def scan_dependency_graph(
    cccl_repo: str | Path | None = None,
    *,
    include_root_rel: str | Path = HEADER_ROOT_REL,
    symbol_dependency_rules: Sequence[Mapping] | None = None,
) -> HeaderDependencyGraphReport:
    """Scan CCCL headers and build an in-tree dependency graph."""
    inventory = scan_header_inventory(
        cccl_repo,
        include_root_rel=include_root_rel,
        symbol_dependency_rules=symbol_dependency_rules,
    )
    # build_dependency_graph_report derives the namespace from inventory.header_root.
    return build_dependency_graph_report(inventory)


def write_dependency_graph_report(
    report: HeaderDependencyGraphReport,
    output_dir: str | Path,
    *,
    filename: str = DEFAULT_DEP_GRAPH_REPORT_NAME,
) -> Path:
    name = Path(filename)
    if name.is_absolute() or len(name.parts) != 1:
        raise ValueError("dependency graph report filename must be a file name under outputs/")
    path = Path(output_dir) / name
    payload = json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
    save_text(path, payload + "\n")
    return path
