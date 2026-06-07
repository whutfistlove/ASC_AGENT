"""Fixture tests for the machine-readable migration status report."""

from __future__ import annotations

import json

import pytest

from core.dep_graph import scan_dependency_graph
from core.inventory import scan_header_inventory
from core.migration_status import (
    parse_migration_ledger_statuses,
    build_migration_status_report,
    write_migration_status_report,
)
from core.test_index import scan_test_index


def _seed_cccl(tmp_path):
    root = tmp_path / "cccl"
    include_root = root / "libcudacxx" / "include" / "cuda" / "std"
    test_root = root / "libcudacxx" / "test" / "libcudacxx" / "std"

    (include_root / "__algorithm").mkdir(parents=True)
    (include_root / "__utility").mkdir(parents=True)
    (include_root / "__algorithm" / "max.h").write_text(
        "#include <cuda/std/__utility/move.h>\n",
        encoding="utf-8",
    )
    (include_root / "__algorithm" / "needs_pair.h").write_text(
        "#include <cuda/std/__utility/pair.h>\n",
        encoding="utf-8",
    )
    (include_root / "__algorithm" / "min.h").write_text("// pending\n", encoding="utf-8")
    (include_root / "__utility" / "move.h").write_text("// move\n", encoding="utf-8")
    (include_root / "__utility" / "pair.h").write_text("// pair\n", encoding="utf-8")
    (include_root / "algorithm").write_text(
        "#include <cuda/std/__algorithm/max.h>\n",
        encoding="utf-8",
    )

    test_dir = test_root / "algorithms" / "alg.min.max"
    test_dir.mkdir(parents=True)
    (test_dir / "max.pass.cpp").write_text(
        "#include <cuda/std/__algorithm/max.h>\n",
        encoding="utf-8",
    )
    (test_dir / "orphan.pass.cpp").write_text(
        "#include <cuda/std/__algorithm/missing.h>\n",
        encoding="utf-8",
    )
    return root


def _seed_target(tmp_path):
    target = tmp_path / "accl"
    include_root = target / "libascendcxx" / "include" / "ascend" / "std"
    host_root = target / "libascendcxx" / "test" / "libascendcxx" / "ascend" / "host"
    kernel_root = target / "libascendcxx" / "test" / "libascendcxx" / "ascend" / "kernel"

    (include_root / "__algorithm").mkdir(parents=True)
    (include_root / "__utility").mkdir(parents=True)
    (include_root / "__algorithm" / "max.h").write_text("// max\n", encoding="utf-8")
    (include_root / "__algorithm" / "needs_pair.h").write_text("// needs pair\n", encoding="utf-8")
    (include_root / "__utility" / "move.h").write_text("// move\n", encoding="utf-8")
    (include_root / "__algorithm" / "synthetic.h").write_text("// synthetic\n", encoding="utf-8")
    (include_root / "algorithm").write_text("// public\n", encoding="utf-8")

    host_root.mkdir(parents=True)
    (host_root / "max_tests.cpp").write_text("int main(){return 0;}\n", encoding="utf-8")
    (kernel_root / "max_example").mkdir(parents=True)
    (kernel_root / "max_example" / "kernel_spec.json").write_text("{}\n", encoding="utf-8")
    return target


def _seed_ledger(tmp_path):
    ledger = tmp_path / "migration_ledger.md"
    ledger.write_text(
        "\n".join(
            [
                "| Source area | Item | Status | Notes |",
                "| --- | --- | --- | --- |",
                "| `__algorithm` | `max.h` | kernel_passed | checked |",
                "| `__algorithm` | `needs_pair.h` | generated | missing dep |",
                "| `__algorithm` | `min.h` | host_passed | target missing |",
                "",
                "| Public header | Status | Exposed validated components | Notes |",
                "| --- | --- | --- | --- |",
                "| `ascend/std/algorithm` | host_passed | `max` | checked |",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return ledger


def test_parse_migration_ledger_statuses(tmp_path):
    ledger = _seed_ledger(tmp_path)
    entries = {entry.key: entry.status for entry in parse_migration_ledger_statuses(ledger)}

    assert entries["__algorithm/max.h"] == "kernel_passed"
    assert entries["__algorithm/needs_pair.h"] == "generated"
    assert entries["__algorithm/min.h"] == "host_passed"
    assert entries["libascendcxx/include/ascend/std/algorithm"] == "host_passed"


def test_build_migration_status_report_from_fixture(tmp_path):
    cccl = _seed_cccl(tmp_path)
    target = _seed_target(tmp_path)
    ledger = _seed_ledger(tmp_path)

    report = build_migration_status_report(
        inventory=scan_header_inventory(cccl),
        test_index=scan_test_index(cccl),
        dep_graph=scan_dependency_graph(cccl),
        target_repo=target,
        ledger_path=ledger,
    )
    by_header = {entry.source_header: entry for entry in report.headers}

    assert by_header["__algorithm/max.h"].status == "kernel_passed"
    assert by_header["__algorithm/max.h"].host_test_exists is True
    assert by_header["__algorithm/max.h"].kernel_spec_exists is True
    assert by_header["__algorithm/max.h"].mapped_tests == [
        "algorithms/alg.min.max/max.pass.cpp"
    ]

    needs_pair = by_header["__algorithm/needs_pair.h"]
    assert needs_pair.status == "generated"
    assert needs_pair.missing_dependencies == ["__utility/pair.h"]
    assert report.missing_dependencies[0].dependency_target_relpath == (
        "libascendcxx/include/ascend/std/__utility/pair.h"
    )

    assert by_header["__algorithm/min.h"].status == "pending"
    assert by_header["__algorithm/min.h"].notes == [
        "ledger_status_ignored_because_target_header_is_missing"
    ]

    assert by_header["algorithm"].status == "host_passed"
    assert report.summary()["migrated_header_count"] == 4
    assert report.summary()["missing_dependency_count"] == 1
    assert report.summary()["unmapped_test_count"] == 1
    assert [entry.target_relpath for entry in report.target_only_headers] == [
        "libascendcxx/include/ascend/std/__algorithm/synthetic.h"
    ]


def test_write_migration_status_report_is_deterministic_json(tmp_path):
    cccl = _seed_cccl(tmp_path)
    target = _seed_target(tmp_path)
    ledger = _seed_ledger(tmp_path)
    report = build_migration_status_report(
        inventory=scan_header_inventory(cccl),
        test_index=scan_test_index(cccl),
        dep_graph=scan_dependency_graph(cccl),
        target_repo=target,
        ledger_path=ledger,
    )

    first = write_migration_status_report(report, tmp_path / "outputs")
    first_text = first.read_text(encoding="utf-8")
    second = write_migration_status_report(report, tmp_path / "outputs")
    second_text = second.read_text(encoding="utf-8")

    assert first == second
    assert first_text == second_text
    data = json.loads(first_text)
    assert data["summary"]["status_counts"]["kernel_passed"] == 1
    assert data["headers"][0]["source_header"] == "__algorithm/max.h"


def test_write_migration_status_report_rejects_paths_outside_outputs(tmp_path):
    cccl = _seed_cccl(tmp_path)
    target = _seed_target(tmp_path)
    report = build_migration_status_report(
        inventory=scan_header_inventory(cccl),
        test_index=scan_test_index(cccl),
        dep_graph=scan_dependency_graph(cccl),
        target_repo=target,
    )

    with pytest.raises(ValueError):
        write_migration_status_report(report, tmp_path / "outputs", filename="../outside.json")
