"""Read-only inventory for migrated ACCL asc-stl headers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from core.analysis.path_mapper import normalize_path_str

_ASC_STD_INCLUDE_RE = re.compile(
    r'^\s*#\s*include\s*[<"]\s*(asc/std/[^>"]+)\s*[>"]',
    re.MULTILINE,
)


@dataclass(frozen=True)
class TargetHeaderEntry:
    target_relpath: str
    std_relpath: str
    includes: list[str]
    dependencies: list[str]
    missing_include_dependencies: list[str]
    missing_include_paths: list[str]

    def to_dict(self) -> dict:
        return {
            "dependencies": list(self.dependencies),
            "includes": list(self.includes),
            "missing_include_dependencies": list(self.missing_include_dependencies),
            "missing_include_paths": list(self.missing_include_paths),
            "std_relpath": self.std_relpath,
            "target_relpath": self.target_relpath,
        }


@dataclass(frozen=True)
class TargetHeaderInventoryReport:
    target_repo: str
    target_root: str
    headers: list[TargetHeaderEntry]

    def summary(self) -> dict:
        broken = [entry for entry in self.headers if entry.missing_include_dependencies]
        return {
            "broken_header_count": len(broken),
            "header_count": len(self.headers),
            "missing_include_count": sum(len(entry.missing_include_dependencies) for entry in self.headers),
        }

    def to_dict(self) -> dict:
        return {
            "headers": [entry.to_dict() for entry in self.headers],
            "summary": self.summary(),
            "target_repo": self.target_repo,
            "target_root": self.target_root,
        }


def parse_asc_std_includes(text: str) -> list[str]:
    """Return sorted unique `asc/std/...` includes from ACCL target code."""
    return sorted(set(_ASC_STD_INCLUDE_RE.findall(text)))


def asc_include_to_std_relpath(include_path: str) -> str | None:
    prefix = "asc/std/"
    if not include_path.startswith(prefix):
        return None
    return include_path[len(prefix):]


def scan_target_header_inventory(
    target_repo: str | Path,
    *,
    target_repo_prefix: str = "asc-stl/include/asc/std",
) -> TargetHeaderInventoryReport:
    """Scan ACCL target headers and check their in-tree `asc/std/...` includes."""
    repo = Path(target_repo).resolve()
    root = repo / normalize_path_str(target_repo_prefix)
    if not root.is_dir():
        return TargetHeaderInventoryReport(target_repo=str(repo), target_root=str(root), headers=[])

    paths = sorted(path for path in root.rglob("*") if path.is_file())
    known = {path.relative_to(root).as_posix() for path in paths}
    entries: list[TargetHeaderEntry] = []
    for path in paths:
        std_relpath = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        includes = parse_asc_std_includes(text)
        dependencies = sorted(
            dep for dep in (asc_include_to_std_relpath(include) for include in includes)
            if dep is not None and dep in known
        )
        missing = sorted(
            dep for dep in (asc_include_to_std_relpath(include) for include in includes)
            if dep is not None and dep not in known
        )
        entries.append(
            TargetHeaderEntry(
                target_relpath=(Path(normalize_path_str(target_repo_prefix)) / std_relpath).as_posix(),
                std_relpath=std_relpath,
                includes=includes,
                dependencies=dependencies,
                missing_include_dependencies=missing,
                missing_include_paths=[f"asc/std/{dep}" for dep in missing],
            )
        )
    return TargetHeaderInventoryReport(
        target_repo=str(repo),
        target_root=str(root),
        headers=entries,
    )
