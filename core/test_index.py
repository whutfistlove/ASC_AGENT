"""Deterministic CCCL libcudacxx test indexing for real upstream scans."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from core.inventory import (
    HEADER_ROOT_REL,
    include_to_header_relpath,
    is_env_file,
    parse_cuda_std_includes,
    resolve_cccl_repo,
    scan_header_inventory,
)
from core.utils import save_text

TEST_ROOT_REL = Path("libcudacxx/test/libcudacxx/std")
DEFAULT_TEST_INDEX_REPORT_NAME = "cccl_test_index.json"

TEST_KIND_SUFFIXES: tuple[tuple[str, str], ...] = (
    (".pass.cpp", "pass"),
    (".verify.cpp", "verify"),
    (".fail.cpp", "fail"),
)
HELPER_HEADER_SUFFIXES = (".h", ".hpp", ".cuh")


@dataclass(frozen=True)
class CCCLTestIndexEntry:
    relative_path: str
    filename: str
    directory: str
    kind: str
    includes: list[str]
    candidate_headers: list[str]
    unknown_cuda_std_includes: list[str]

    def to_dict(self) -> dict:
        return {
            "candidate_headers": list(self.candidate_headers),
            "directory": self.directory,
            "filename": self.filename,
            "includes": list(self.includes),
            "kind": self.kind,
            "relative_path": self.relative_path,
            "unknown_cuda_std_includes": list(self.unknown_cuda_std_includes),
        }


@dataclass(frozen=True)
class HeaderTestMapping:
    header: str
    include: str
    tests: list[str]

    def to_dict(self) -> dict:
        return {
            "header": self.header,
            "include": self.include,
            "test_count": len(self.tests),
            "tests": list(self.tests),
        }


@dataclass(frozen=True)
class CCCLTestIndexReport:
    cccl_repo: str
    header_root: str
    test_root: str
    tests: list[CCCLTestIndexEntry]
    helper_headers: list[CCCLTestIndexEntry]
    mappings: list[HeaderTestMapping]
    unmapped_headers: list[str]
    unmapped_tests: list[str]

    def summary(self) -> dict:
        by_kind: dict[str, int] = {}
        for entry in self.tests:
            by_kind[entry.kind] = by_kind.get(entry.kind, 0) + 1
        return {
            "by_kind": dict(sorted(by_kind.items())),
            "header_count": len(self.unmapped_headers) + len(self.mappings),
            "helper_header_count": len(self.helper_headers),
            "mapped_header_count": len(self.mappings),
            "test_count": len(self.tests),
            "unmapped_header_count": len(self.unmapped_headers),
            "unmapped_test_count": len(self.unmapped_tests),
        }

    def to_dict(self) -> dict:
        return {
            "cccl_repo": self.cccl_repo,
            "header_root": self.header_root,
            "helper_headers": [h.to_dict() for h in self.helper_headers],
            "mappings": [m.to_dict() for m in self.mappings],
            "summary": self.summary(),
            "test_root": self.test_root,
            "tests": [t.to_dict() for t in self.tests],
            "unmapped_headers": list(self.unmapped_headers),
            "unmapped_tests": list(self.unmapped_tests),
        }


def classify_test_kind(path: str | Path) -> str | None:
    """Classify libcudacxx test files by CCCL's pass/verify/fail suffixes."""
    name = Path(path).name
    for suffix, kind in TEST_KIND_SUFFIXES:
        if name.endswith(suffix):
            return kind
    return None


def is_helper_header(path: str | Path) -> bool:
    return Path(path).suffix in HELPER_HEADER_SUFFIXES


def _candidate_headers(includes: list[str], known_headers: set[str]) -> tuple[list[str], list[str]]:
    candidates: set[str] = set()
    unknown: set[str] = set()
    for include_path in includes:
        relpath = include_to_header_relpath(include_path)
        if relpath is None:
            continue
        if relpath in known_headers:
            candidates.add(relpath)
        else:
            unknown.add(include_path)
    return sorted(candidates), sorted(unknown)


def _entry(path: Path, test_root: Path, *, kind: str, known_headers: set[str]) -> CCCLTestIndexEntry:
    relative_path = path.relative_to(test_root).as_posix()
    includes = parse_cuda_std_includes(path.read_text(encoding="utf-8", errors="replace"))
    candidates, unknown = _candidate_headers(includes, known_headers)
    return CCCLTestIndexEntry(
        relative_path=relative_path,
        filename=path.name,
        directory=Path(relative_path).parent.as_posix(),
        kind=kind,
        includes=includes,
        candidate_headers=candidates,
        unknown_cuda_std_includes=unknown,
    )


def _build_mappings(tests: list[CCCLTestIndexEntry]) -> list[HeaderTestMapping]:
    by_header: dict[str, set[str]] = {}
    for test in tests:
        for header in test.candidate_headers:
            by_header.setdefault(header, set()).add(test.relative_path)
    return [
        HeaderTestMapping(
            header=header,
            include=f"cuda/std/{header}",
            tests=sorted(paths),
        )
        for header, paths in sorted(by_header.items())
    ]


def scan_test_index(
    cccl_repo: str | Path | None = None,
    *,
    include_root_rel: str | Path = HEADER_ROOT_REL,
    test_root_rel: str | Path = TEST_ROOT_REL,
) -> CCCLTestIndexReport:
    """Scan real libcudacxx tests without modifying the CCCL repository."""
    repo = resolve_cccl_repo(cccl_repo)
    header_report = scan_header_inventory(repo, include_root_rel=include_root_rel)
    known_headers = {h.relative_path for h in header_report.headers}

    test_root = repo / Path(test_root_rel)
    if not test_root.is_dir():
        raise FileNotFoundError(f"CCCL test root not found: {test_root}")

    tests: list[CCCLTestIndexEntry] = []
    helper_headers: list[CCCLTestIndexEntry] = []
    for path in sorted(p for p in test_root.rglob("*") if p.is_file() and not is_env_file(p)):
        kind = classify_test_kind(path)
        if kind is not None:
            tests.append(_entry(path, test_root, kind=kind, known_headers=known_headers))
        elif is_helper_header(path):
            helper_headers.append(_entry(path, test_root, kind="helper_header", known_headers=known_headers))

    mappings = _build_mappings(tests)
    mapped_headers = {mapping.header for mapping in mappings}
    unmapped_headers = sorted(known_headers - mapped_headers)
    unmapped_tests = sorted(test.relative_path for test in tests if not test.candidate_headers)

    return CCCLTestIndexReport(
        cccl_repo=str(repo),
        header_root=header_report.header_root,
        test_root=str(test_root),
        tests=tests,
        helper_headers=helper_headers,
        mappings=mappings,
        unmapped_headers=unmapped_headers,
        unmapped_tests=unmapped_tests,
    )


def write_test_index_report(
    report: CCCLTestIndexReport,
    output_dir: str | Path,
    *,
    filename: str = DEFAULT_TEST_INDEX_REPORT_NAME,
) -> Path:
    name = Path(filename)
    if name.is_absolute() or len(name.parts) != 1:
        raise ValueError("test index report filename must be a file name under outputs/")
    path = Path(output_dir) / name
    payload = json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
    save_text(path, payload + "\n")
    return path
