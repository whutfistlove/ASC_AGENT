"""Deterministic CCCL header include dependency graph support."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from core.inventory import (
    HEADER_ROOT_REL,
    HeaderInventoryReport,
    include_to_header_relpath,
    scan_header_inventory,
)
from core.utils import save_text

DEFAULT_DEP_GRAPH_REPORT_NAME = "cccl_dep_graph.json"


@dataclass(frozen=True)
class HeaderDependencyEntry:
    header: str
    include: str
    dependencies: list[str]
    dependency_includes: list[str]
    unknown_cuda_std_includes: list[str]

    def to_dict(self) -> dict:
        return {
            "dependencies": list(self.dependencies),
            "dependency_includes": list(self.dependency_includes),
            "header": self.header,
            "include": self.include,
            "unknown_cuda_std_includes": list(self.unknown_cuda_std_includes),
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
        return {
            "cycle_count": len(self.cycles),
            "edge_count": edge_count,
            "has_cycles": bool(self.cycles),
            "header_count": len(self.graph),
            "topological_order_count": len(self.topological_order),
            "unknown_cuda_std_include_count": unknown_count,
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


def _dependency_entry(header: str, includes: list[str], known_headers: set[str]) -> HeaderDependencyEntry:
    dependencies: set[str] = set()
    unknown: set[str] = set()
    for include_path in includes:
        relpath = include_to_header_relpath(include_path)
        if relpath is None:
            continue
        if relpath in known_headers:
            dependencies.add(relpath)
        else:
            unknown.add(include_path)
    deps = sorted(dependencies)
    return HeaderDependencyEntry(
        header=header,
        include=f"cuda/std/{header}",
        dependencies=deps,
        dependency_includes=[f"cuda/std/{dep}" for dep in deps],
        unknown_cuda_std_includes=sorted(unknown),
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
    """Build a header dependency graph from a header inventory report."""
    known_headers = {header.relative_path for header in inventory.headers}
    entries = [
        _dependency_entry(header.relative_path, header.includes, known_headers)
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
) -> HeaderDependencyGraphReport:
    """Scan CCCL headers and build an in-tree include dependency graph."""
    inventory = scan_header_inventory(cccl_repo, include_root_rel=include_root_rel)
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
