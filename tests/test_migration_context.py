"""Fixture tests for bounded AI migration context pack generation."""

from __future__ import annotations

import json

import pytest

from core.dep_graph import scan_dependency_graph
from core.inventory import scan_header_inventory
from core.migration_context import (
    build_migration_context_pack,
    default_context_pack_filename,
    write_migration_context_pack,
)
from core.migration_status import build_migration_status_report
from core.test_index import scan_test_index


def _seed_cccl(tmp_path):
    root = tmp_path / "cccl"
    include_root = root / "libcudacxx" / "include" / "cuda" / "std"
    test_root = root / "libcudacxx" / "test" / "libcudacxx" / "std"
    (include_root / "__algorithm").mkdir(parents=True)
    (include_root / "__utility").mkdir(parents=True)
    (include_root / "__algorithm" / "all_of.h").write_text(
        "\n".join(
            [
                "#include <cuda/std/__algorithm/pred.h>",
                "namespace cuda { namespace std {",
                "template <class It, class Pred> bool all_of(It first, It last, Pred pred);",
                "}}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (include_root / "__algorithm" / "pred.h").write_text(
        "#include <cuda/std/__utility/move.h>\n",
        encoding="utf-8",
    )
    (include_root / "__algorithm" / "max.h").write_text(
        "template <class T> T max(T a, T b);\n",
        encoding="utf-8",
    )
    (include_root / "__algorithm" / "min.h").write_text(
        "template <class T> T min(T a, T b);\n",
        encoding="utf-8",
    )
    (include_root / "__utility" / "move.h").write_text("// move\n", encoding="utf-8")
    (include_root / ".env").write_text("SECRET=do-not-read\n", encoding="utf-8")

    test_dir = test_root / "algorithms" / "all_of"
    test_dir.mkdir(parents=True)
    (test_dir / "all_of.pass.cpp").write_text(
        "#include <cuda/std/__algorithm/all_of.h>\nint main() { return 0; }\n",
        encoding="utf-8",
    )
    (test_root / ".env").write_text("SECRET=do-not-read\n", encoding="utf-8")
    return root


def _seed_target(tmp_path):
    target = tmp_path / "accl"
    include_root = target / "libascendcxx" / "include" / "ascend" / "std" / "__algorithm"
    include_root.mkdir(parents=True)
    (include_root / "all_of.h").write_text("// generated all_of\n", encoding="utf-8")
    (include_root / "max.h").write_text("// validated max\n", encoding="utf-8")
    (include_root / "min.h").write_text("// generated min\n", encoding="utf-8")
    (target / "libascendcxx" / "include" / "ascend" / "std" / "__utility").mkdir(parents=True)
    (
        target / "libascendcxx" / "include" / "ascend" / "std" / "__utility" / "move.h"
    ).write_text("// move\n", encoding="utf-8")
    return target


def _seed_ledger(tmp_path):
    ledger = tmp_path / "migration_ledger.md"
    ledger.write_text(
        "\n".join(
            [
                "| Source area | Item | Status | Notes |",
                "| --- | --- | --- | --- |",
                "| `__algorithm` | `all_of.h` | generated | context target exists |",
                "| `__algorithm` | `max.h` | kernel_passed | validated example |",
                "| `__algorithm` | `min.h` | generated | not validated |",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return ledger


def _seed_examples(tmp_path):
    root = tmp_path / "examples"
    headers = root / "headers"
    tests = root / "tests"
    headers.mkdir(parents=True)
    tests.mkdir(parents=True)
    (headers / "max.cccl.h").write_text("template <class T> T max(T a, T b);\n", encoding="utf-8")
    (headers / "max.accl.h").write_text("template <class T> T max(T a, T b);\n", encoding="utf-8")
    (headers / "min.cccl.h").write_text("template <class T> T min(T a, T b);\n", encoding="utf-8")
    (headers / "min.accl.h").write_text("template <class T> T min(T a, T b);\n", encoding="utf-8")
    (tests / "max.cccl.pass.cpp").write_text("#include <cuda/std/__algorithm/max.h>\n", encoding="utf-8")
    (tests / "max.accl_host.cpp").write_text("int main(){return 0;}\n", encoding="utf-8")
    (tests / "max.accl_kernel_spec.json").write_text('{"dtype":"int32_t"}\n', encoding="utf-8")
    return root


def _build_reports(tmp_path):
    cccl = _seed_cccl(tmp_path)
    target = _seed_target(tmp_path)
    ledger = _seed_ledger(tmp_path)
    inventory = scan_header_inventory(cccl)
    test_index = scan_test_index(cccl)
    dep_graph = scan_dependency_graph(cccl)
    status_report = build_migration_status_report(
        inventory=inventory,
        test_index=test_index,
        dep_graph=dep_graph,
        target_repo=target,
        ledger_path=ledger,
    )
    return cccl, target, inventory, test_index, dep_graph, status_report


def test_build_migration_context_pack_from_fixture(tmp_path):
    _, target, inventory, test_index, dep_graph, status_report = _build_reports(tmp_path)
    examples = _seed_examples(tmp_path)

    pack = build_migration_context_pack(
        entry_header="__algorithm/all_of.h",
        inventory=inventory,
        test_index=test_index,
        dep_graph=dep_graph,
        status_report=status_report,
        target_repo=target,
        examples_root=examples,
        limits={
            "max_source_chars": 120,
            "max_accl_chars": 80,
            "max_sibling_chars": 80,
            "max_test_chars": 80,
            "max_example_chars": 80,
            "max_siblings": 2,
            "max_tests": 2,
            "max_examples": 2,
        },
    )

    assert pack["schema_version"] == 1
    assert pack["entry_header"] == "__algorithm/all_of.h"
    assert pack["source_header"]["metadata"]["module"] == "__algorithm"
    assert pack["source_header"]["content"]["truncated"] is True
    assert pack["dependency_closure"]["direct_dependencies"] == ["__algorithm/pred.h"]
    assert pack["dependency_closure"]["leaf_first"] == [
        "__utility/move.h",
        "__algorithm/pred.h",
    ]
    assert pack["dependency_closure"]["closure_size"] == 2
    assert [node["source_header"] for node in pack["dependency_closure"]["nodes"]] == [
        "__utility/move.h",
        "__algorithm/pred.h",
    ]

    assert pack["existing_accl_counterpart"]["exists"] is True
    assert pack["existing_accl_counterpart"]["target_relpath"] == (
        "libascendcxx/include/ascend/std/__algorithm/all_of.h"
    )
    assert [
        sibling["target_relpath"]
        for sibling in pack["nearby_accl_sibling_headers"]
    ] == [
        "libascendcxx/include/ascend/std/__algorithm/max.h",
        "libascendcxx/include/ascend/std/__algorithm/min.h",
    ]

    assert [test["relative_path"] for test in pack["mapped_upstream_tests"]] == [
        "algorithms/all_of/all_of.pass.cpp"
    ]
    assert pack["mapped_upstream_tests"][0]["metadata"]["kind"] == "pass"

    assert [example["name"] for example in pack["relevant_validated_examples"]] == ["max"]
    assert pack["relevant_validated_examples"][0]["status"] == "kernel_passed"
    assert "test_example" in pack["relevant_validated_examples"][0]
    assert pack["ledger_status_evidence"]["entry_status"]["status"] == "generated"
    assert pack["ledger_status_evidence"]["ledger_entries"][0]["key"] == "__algorithm/all_of.h"
    assert pack["bounds"]["target_repo"] == str(target.resolve())


def test_write_migration_context_pack_is_deterministic_json(tmp_path):
    _, target, inventory, test_index, dep_graph, status_report = _build_reports(tmp_path)
    examples = _seed_examples(tmp_path)
    pack = build_migration_context_pack(
        entry_header="__algorithm/all_of.h",
        inventory=inventory,
        test_index=test_index,
        dep_graph=dep_graph,
        status_report=status_report,
        target_repo=target,
        examples_root=examples,
    )

    first = write_migration_context_pack(pack, tmp_path / "outputs")
    first_text = first.read_text(encoding="utf-8")
    second = write_migration_context_pack(pack, tmp_path / "outputs")
    second_text = second.read_text(encoding="utf-8")

    assert first.name == default_context_pack_filename("__algorithm/all_of.h")
    assert first == second
    assert first_text == second_text
    data = json.loads(first_text)
    assert data["entry_header"] == "__algorithm/all_of.h"


def test_write_migration_context_pack_rejects_paths_outside_outputs(tmp_path):
    _, target, inventory, test_index, dep_graph, status_report = _build_reports(tmp_path)
    examples = _seed_examples(tmp_path)
    pack = build_migration_context_pack(
        entry_header="__algorithm/all_of.h",
        inventory=inventory,
        test_index=test_index,
        dep_graph=dep_graph,
        status_report=status_report,
        target_repo=target,
        examples_root=examples,
    )

    with pytest.raises(ValueError):
        write_migration_context_pack(pack, tmp_path / "outputs", filename="../outside.json")


def test_inventory_and_test_index_skip_env_files(tmp_path):
    cccl = _seed_cccl(tmp_path)

    inventory = scan_header_inventory(cccl)
    test_index = scan_test_index(cccl)

    assert ".env" not in {header.relative_path for header in inventory.headers}
    assert all(".env" not in test.relative_path for test in test_index.tests)
