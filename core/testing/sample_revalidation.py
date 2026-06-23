"""Node 6 sample revalidation against the real CCCL tree."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from core.analysis.dep_graph import scan_dependency_graph
from core.analysis.inventory import scan_header_inventory
from core.analysis.test_index import CCCLTestIndexEntry, scan_test_index
from core.common.utils import save_text

DEFAULT_SAMPLE_REVALIDATION_REPORT_NAME = "sample_revalidation.json"


@dataclass(frozen=True)
class SampleTarget:
    name: str
    upstream_header: str
    target_header: str
    test_directory: str


DEFAULT_SAMPLE_TARGETS: tuple[SampleTarget, ...] = (
    SampleTarget(
        name="max",
        upstream_header="__algorithm/max.h",
        target_header="asc-stl/include/asc/std/__algorithm/max.h",
        test_directory="algorithms/alg.sorting/alg.min.max",
    ),
    SampleTarget(
        name="min",
        upstream_header="__algorithm/min.h",
        target_header="asc-stl/include/asc/std/__algorithm/min.h",
        test_directory="algorithms/alg.sorting/alg.min.max",
    ),
    SampleTarget(
        name="clamp",
        upstream_header="__algorithm/clamp.h",
        target_header="asc-stl/include/asc/std/__algorithm/clamp.h",
        test_directory="algorithms/alg.sorting/alg.clamp",
    ),
    SampleTarget(
        name="swap",
        upstream_header="__utility/swap.h",
        target_header="asc-stl/include/asc/std/__utility/swap.h",
        test_directory="utilities/utility/utility.swap",
    ),
    SampleTarget(
        name="minmax",
        upstream_header="__algorithm/minmax.h",
        target_header="asc-stl/include/asc/std/__algorithm/minmax.h",
        test_directory="algorithms/alg.sorting/alg.min.max",
    ),
)


def _stem_matches_sample(stem: str, sample_name: str) -> bool:
    """Match operation-specific tests without letting `min` match `minmax`."""
    return (
        stem == sample_name
        or stem.startswith(f"{sample_name}_")
        or stem.startswith(f"{sample_name}.")
    )


def _candidate_tests(entries: list[CCCLTestIndexEntry], target: SampleTarget) -> list[str]:
    paths: list[str] = []
    for entry in entries:
        if entry.directory != target.test_directory:
            continue
        stem = entry.filename
        for suffix in (".pass.cpp", ".verify.cpp", ".fail.cpp"):
            if stem.endswith(suffix):
                stem = stem[: -len(suffix)]
                break
        if _stem_matches_sample(stem, target.name):
            paths.append(entry.relative_path)
    return sorted(paths)


def _test_stem(path: str) -> str:
    stem = Path(path).name
    for suffix in (".pass.cpp", ".verify.cpp", ".fail.cpp"):
        if stem.endswith(suffix):
            return stem[: -len(suffix)]
    return stem


def _scaffold_applicable_tests(candidate_tests: list[str], sample_name: str) -> list[str]:
    if sample_name in {"max", "min", "minmax"}:
        stems = {sample_name, f"{sample_name}_comp"}
    elif sample_name == "clamp":
        stems = {"clamp", "clamp.comp"}
    elif sample_name == "swap":
        stems = {"swap", "swap_array"}
    else:
        stems = {sample_name}
    return [path for path in candidate_tests if _test_stem(path) in stems]


def build_sample_revalidation_report(
    cccl_repo: str | Path | None = None,
    *,
    target_repo: str | Path | None = None,
    samples: tuple[SampleTarget, ...] = DEFAULT_SAMPLE_TARGETS,
    symbol_dependency_rules: Sequence[Mapping] | None = None,
) -> dict:
    inventory = scan_header_inventory(cccl_repo, symbol_dependency_rules=symbol_dependency_rules)
    test_index = scan_test_index(cccl_repo)
    dep_graph = scan_dependency_graph(cccl_repo, symbol_dependency_rules=symbol_dependency_rules)

    headers = {entry.relative_path: entry for entry in inventory.headers}
    mappings = {mapping.header: mapping for mapping in test_index.mappings}
    graph = {entry.header: entry for entry in dep_graph.graph}
    target_root = Path(target_repo).resolve() if target_repo else None

    sample_entries = []
    for target in samples:
        header = headers.get(target.upstream_header)
        deps = graph.get(target.upstream_header)
        mapped = mappings.get(target.upstream_header)
        target_path = target_root / target.target_header if target_root else None
        host_test = (
            target_root
            / "asc-stl"
            / "test"
            / "asc-stl"
            / "asc"
            / "host"
            / f"{target.name}_tests.cpp"
            if target_root
            else None
        )
        kernel_spec = (
            target_root
            / "asc-stl"
            / "test"
            / "asc-stl"
            / "asc"
            / "kernel"
            / f"{target.name}_example"
            / "kernel_spec.json"
            if target_root
            else None
        )
        candidate_tests = _candidate_tests(test_index.tests, target)
        applicable_tests = _scaffold_applicable_tests(candidate_tests, target.name)
        deferred_tests = sorted(set(candidate_tests) - set(applicable_tests))
        sample_entries.append(
            {
                "candidate_tests": candidate_tests,
                "deferred_upstream_tests": deferred_tests,
                "dependency_headers": list(deps.dependencies) if deps else [],
                "direct_include_mapped_tests": list(mapped.tests) if mapped else [],
                "header_exists": header is not None,
                "header_includes": list(header.includes) if header else [],
                "kernel_spec_exists": bool(kernel_spec and kernel_spec.is_file()),
                "name": target.name,
                "scaffold_applicable_tests": applicable_tests,
                "status": "mapped" if header and candidate_tests else "needs_mapping",
                "target_header": target.target_header,
                "target_header_exists": bool(target_path and target_path.is_file()),
                "host_test_exists": bool(host_test and host_test.is_file()),
                "test_directory": target.test_directory,
                "upstream_header": target.upstream_header,
                "unknown_cuda_std_includes": list(deps.unknown_cuda_std_includes) if deps else [],
            }
        )

    return {
        "cccl_repo": inventory.cccl_repo,
        "header_root": inventory.header_root,
        "samples": sample_entries,
        "summary": {
            "mapped_sample_count": sum(1 for entry in sample_entries if entry["status"] == "mapped"),
            "sample_count": len(sample_entries),
        },
        "test_root": test_index.test_root,
    }


def write_sample_revalidation_report(
    report: dict,
    output_dir: str | Path,
    *,
    filename: str = DEFAULT_SAMPLE_REVALIDATION_REPORT_NAME,
) -> Path:
    name = Path(filename)
    if name.is_absolute() or len(name.parts) != 1:
        raise ValueError("sample revalidation filename must be a file name under outputs/")
    path = Path(output_dir) / name
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    save_text(path, payload + "\n")
    return path
