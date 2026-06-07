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

from core.dep_graph import HeaderDependencyGraphReport, scan_dependency_graph
from core.inventory import HeaderInventoryReport, scan_header_inventory
from core.path_mapper import apply_segment_substitutions, normalize_path_str
from core.test_index import CCCLTestIndexReport, scan_test_index
from core.utils import save_text

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
_TARGET_STD_PREFIX = "libascendcxx/include/ascend/std"


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

    def to_dict(self) -> dict:
        return {
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

    def to_dict(self) -> dict:
        return {
            "dependency": self.dependency,
            "dependency_target_relpath": self.dependency_target_relpath,
            "header": self.header,
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

    def summary(self) -> dict:
        status_counts = {status: 0 for status in STATUS_VALUES}
        for entry in self.headers:
            status_counts[entry.status] += 1
        migrated_headers = [entry.source_header for entry in self.headers if entry.status != "pending"]
        return {
            "dep_graph_cycle_count": len(self.dep_graph_cycles),
            "header_count": len(self.headers),
            "ledger_entry_count": len(self.ledger_entries),
            "mapped_header_count": len(self.mapped_tests),
            "migrated_header_count": len(migrated_headers),
            "missing_dependency_count": len(self.missing_dependencies),
            "status_counts": status_counts,
            "target_only_header_count": len(self.target_only_headers),
            "unmapped_header_count": len(self.unmapped_headers),
            "unmapped_test_count": len(self.unmapped_tests),
        }

    def to_dict(self) -> dict:
        migrated_headers = [entry.source_header for entry in self.headers if entry.status != "pending"]
        return {
            "cccl_repo": self.cccl_repo,
            "dep_graph_cycles": [list(cycle) for cycle in self.dep_graph_cycles],
            "header_root": self.header_root,
            "headers": [entry.to_dict() for entry in self.headers],
            "ledger_entries": [entry.to_dict() for entry in self.ledger_entries],
            "mapped_tests": list(self.mapped_tests),
            "migrated_headers": migrated_headers,
            "missing_dependencies": [entry.to_dict() for entry in self.missing_dependencies],
            "summary": self.summary(),
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
        if raw.startswith("ascend/std/"):
            keys.add(_TARGET_STD_PREFIX + "/" + raw[len("ascend/std/"):])
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
        elif len(cells) >= 3 and cells[1] in _LEDGER_STATUSES and cells[0].startswith("`ascend/std/"):
            key = _TARGET_STD_PREFIX + "/" + _strip_code(cells[0])[len("ascend/std/"):]
            entries.append(LedgerStatusEntry(key=key, status=cells[1], source=str(path)))
    dedup: dict[str, LedgerStatusEntry] = {}
    for entry in entries:
        previous = dedup.get(entry.key)
        if previous is None or _STATUS_RANK[entry.status] >= _STATUS_RANK[previous.status]:
            dedup[entry.key] = entry
    return [dedup[key] for key in sorted(dedup)]


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
    host_root = target_repo / "libascendcxx/test/libascendcxx/ascend/host"
    return any((host_root / f"{name}_tests.cpp").exists() for name in _algo_names_for_header(source_header))


def _kernel_spec_exists(target_repo: Path, source_header: str) -> bool:
    kernel_root = target_repo / "libascendcxx/test/libascendcxx/ascend/kernel"
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


def _ledger_map(entries: list[LedgerStatusEntry]) -> dict[str, str]:
    return {entry.key: entry.status for entry in entries}


def build_migration_status_report(
    *,
    inventory: HeaderInventoryReport,
    test_index: CCCLTestIndexReport,
    dep_graph: HeaderDependencyGraphReport,
    target_repo: str | Path,
    ledger_path: str | Path | None = None,
    target_repo_prefix: str = _TARGET_STD_PREFIX,
    segment_substitutions: list[dict] | None = None,
) -> MigrationStatusReport:
    target_root = Path(target_repo).resolve()
    ledger_entries = parse_migration_ledger_statuses(ledger_path) if ledger_path else []
    ledger = _ledger_map(ledger_entries)
    test_map = {mapping.header: mapping.tests for mapping in test_index.mappings}
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
        host_exists = _host_test_exists(target_root, header.relative_path)
        kernel_exists = _kernel_spec_exists(target_root, header.relative_path)
        ledger_status = ledger.get(header.relative_path) or ledger.get(target_relpath)
        status = _status_for(
            target_exists=target_exists,
            ledger_status=ledger_status,
            host_test_exists=host_exists,
            kernel_spec_exists=kernel_exists,
        )
        notes: list[str] = []
        if ledger_status and not target_exists:
            notes.append("ledger_status_ignored_because_target_header_is_missing")

        deps = dep_map.get(header.relative_path, [])
        missing: list[str] = []
        for dep in deps:
            dep_target = target_relpath_for_header(
                dep,
                target_repo_prefix=target_repo_prefix,
                segment_substitutions=segment_substitutions,
            )
            if target_exists and not (target_root / dep_target).exists():
                missing.append(dep)
                missing_dependencies.append(
                    MissingDependencyEntry(
                        header=header.relative_path,
                        dependency=dep,
                        dependency_target_relpath=dep_target,
                    )
                )

        headers.append(
            HeaderMigrationStatusEntry(
                source_header=header.relative_path,
                include=f"cuda/std/{header.relative_path}",
                module=header.module,
                shape=header.shape,
                target_relpath=target_relpath,
                target_exists=target_exists,
                status=status,
                ledger_status=ledger_status,
                host_test_exists=host_exists,
                kernel_spec_exists=kernel_exists,
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
            )
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
    )


def scan_migration_status(
    cccl_repo: str | Path | None,
    *,
    target_repo: str | Path,
    ledger_path: str | Path | None = None,
    target_repo_prefix: str = _TARGET_STD_PREFIX,
    segment_substitutions: list[dict] | None = None,
) -> MigrationStatusReport:
    inventory = scan_header_inventory(cccl_repo)
    test_index = scan_test_index(cccl_repo)
    dep_graph = scan_dependency_graph(cccl_repo)
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
