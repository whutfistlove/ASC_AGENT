"""Fixture tests for Node 6 sample revalidation reporting."""

from __future__ import annotations

import json

import pytest

from core.testing.sample_revalidation import (
    SampleTarget,
    build_sample_revalidation_report,
    write_sample_revalidation_report,
)


def _seed_cccl(tmp_path):
    root = tmp_path / "cccl"
    include_root = root / "libcudacxx" / "include" / "cuda" / "std"
    test_root = root / "libcudacxx" / "test" / "libcudacxx" / "std"

    (include_root / "__algorithm").mkdir(parents=True)
    (include_root / "__utility").mkdir(parents=True)
    (include_root / "__algorithm" / "min.h").write_text(
        "#include <cuda/std/__algorithm/comp.h>\n",
        encoding="utf-8",
    )
    (include_root / "__algorithm" / "minmax.h").write_text(
        "#include <cuda/std/__utility/pair.h>\n",
        encoding="utf-8",
    )
    (include_root / "__utility" / "swap.h").write_text(
        "#include <cuda/std/__utility/move.h>\n",
        encoding="utf-8",
    )
    (include_root / "__algorithm" / "comp.h").write_text("// comp\n", encoding="utf-8")
    (include_root / "__utility" / "pair.h").write_text("// pair\n", encoding="utf-8")
    (include_root / "__utility" / "move.h").write_text("// move\n", encoding="utf-8")
    (include_root / "algorithm").write_text("// public algorithm\n", encoding="utf-8")
    (include_root / "utility").write_text("// public utility\n", encoding="utf-8")

    alg_root = test_root / "algorithms" / "alg.sorting" / "alg.min.max"
    alg_root.mkdir(parents=True)
    (alg_root / "min.pass.cpp").write_text(
        "#include <cuda/std/algorithm>\n",
        encoding="utf-8",
    )
    (alg_root / "min_comp.pass.cpp").write_text(
        "#include <cuda/std/algorithm>\n",
        encoding="utf-8",
    )
    (alg_root / "minmax.pass.cpp").write_text(
        "#include <cuda/std/algorithm>\n",
        encoding="utf-8",
    )
    clamp_root = test_root / "algorithms" / "alg.sorting" / "alg.clamp"
    clamp_root.mkdir(parents=True)
    (include_root / "__algorithm" / "clamp.h").write_text("// clamp\n", encoding="utf-8")
    (clamp_root / "clamp.pass.cpp").write_text(
        "#include <cuda/std/algorithm>\n",
        encoding="utf-8",
    )
    (clamp_root / "clamp.comp.pass.cpp").write_text(
        "#include <cuda/std/algorithm>\n",
        encoding="utf-8",
    )

    swap_root = test_root / "utilities" / "utility" / "utility.swap"
    swap_root.mkdir(parents=True)
    (swap_root / "swap.pass.cpp").write_text(
        "#include <cuda/std/utility>\n",
        encoding="utf-8",
    )
    (swap_root / "swap_array.pass.cpp").write_text(
        "#include <cuda/std/utility>\n",
        encoding="utf-8",
    )

    return root


def test_sample_revalidation_maps_public_include_tests_to_private_headers(tmp_path):
    cccl = _seed_cccl(tmp_path)
    target_repo = tmp_path / "accl"
    target_header = target_repo / "asc-stl" / "include" / "asc" / "std" / "__algorithm" / "min.h"
    target_header.parent.mkdir(parents=True)
    target_header.write_text("// accl min\n", encoding="utf-8")
    host_test = (
        target_repo
        / "asc-stl"
        / "test"
        / "asc-stl"
        / "asc"
        / "host"
        / "min_tests.cpp"
    )
    host_test.parent.mkdir(parents=True)
    host_test.write_text("int main(){return 0;}\n", encoding="utf-8")

    samples = (
        SampleTarget(
            name="min",
            upstream_header="__algorithm/min.h",
            target_header="asc-stl/include/asc/std/__algorithm/min.h",
            test_directory="algorithms/alg.sorting/alg.min.max",
        ),
        SampleTarget(
            name="swap",
            upstream_header="__utility/swap.h",
            target_header="asc-stl/include/asc/std/__utility/swap.h",
            test_directory="utilities/utility/utility.swap",
        ),
        SampleTarget(
            name="clamp",
            upstream_header="__algorithm/clamp.h",
            target_header="asc-stl/include/asc/std/__algorithm/clamp.h",
            test_directory="algorithms/alg.sorting/alg.clamp",
        ),
    )
    report = build_sample_revalidation_report(cccl, target_repo=target_repo, samples=samples)
    entries = {entry["name"]: entry for entry in report["samples"]}

    assert entries["min"]["status"] == "mapped"
    assert entries["min"]["candidate_tests"] == [
        "algorithms/alg.sorting/alg.min.max/min.pass.cpp",
        "algorithms/alg.sorting/alg.min.max/min_comp.pass.cpp",
    ]
    assert entries["min"]["scaffold_applicable_tests"] == entries["min"]["candidate_tests"]
    assert entries["min"]["deferred_upstream_tests"] == []
    assert entries["min"]["dependency_headers"] == ["__algorithm/comp.h"]
    assert entries["min"]["direct_include_mapped_tests"] == []
    assert entries["min"]["target_header_exists"] is True
    assert entries["min"]["host_test_exists"] is True

    assert entries["swap"]["candidate_tests"] == [
        "utilities/utility/utility.swap/swap.pass.cpp",
        "utilities/utility/utility.swap/swap_array.pass.cpp",
    ]
    assert entries["clamp"]["candidate_tests"] == [
        "algorithms/alg.sorting/alg.clamp/clamp.comp.pass.cpp",
        "algorithms/alg.sorting/alg.clamp/clamp.pass.cpp",
    ]
    assert entries["clamp"]["scaffold_applicable_tests"] == [
        "algorithms/alg.sorting/alg.clamp/clamp.comp.pass.cpp",
        "algorithms/alg.sorting/alg.clamp/clamp.pass.cpp",
    ]


def test_write_sample_revalidation_report_is_deterministic_json(tmp_path):
    cccl = _seed_cccl(tmp_path)
    samples = (
        SampleTarget(
            name="minmax",
            upstream_header="__algorithm/minmax.h",
            target_header="asc-stl/include/asc/std/__algorithm/minmax.h",
            test_directory="algorithms/alg.sorting/alg.min.max",
        ),
    )
    report = build_sample_revalidation_report(cccl, samples=samples)

    first = write_sample_revalidation_report(report, tmp_path / "outputs")
    first_text = first.read_text(encoding="utf-8")
    second = write_sample_revalidation_report(report, tmp_path / "outputs")
    second_text = second.read_text(encoding="utf-8")

    assert first == second
    assert first_text == second_text
    data = json.loads(first_text)
    assert data["summary"] == {"mapped_sample_count": 1, "sample_count": 1}


def test_write_sample_revalidation_report_rejects_paths_outside_outputs(tmp_path):
    with pytest.raises(ValueError):
        write_sample_revalidation_report({}, tmp_path / "outputs", filename="../outside.json")
