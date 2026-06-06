"""Fixture tests for real CCCL libcudacxx test indexing support."""

from __future__ import annotations

import json

import pytest

from core.test_index import (
    classify_test_kind,
    is_helper_header,
    scan_test_index,
    write_test_index_report,
)


def _seed_cccl_with_tests(tmp_path):
    root = tmp_path / "cccl"
    include_root = root / "libcudacxx" / "include" / "cuda" / "std"
    test_root = root / "libcudacxx" / "test" / "libcudacxx" / "std"

    (include_root / "__algorithm").mkdir(parents=True)
    (include_root / "__utility").mkdir(parents=True)
    (include_root / "__algorithm" / "max.h").write_text("// max\n", encoding="utf-8")
    (include_root / "__algorithm" / "min.h").write_text("// min\n", encoding="utf-8")
    (include_root / "__utility" / "move.h").write_text("// move\n", encoding="utf-8")
    (include_root / "algorithm").write_text("// algorithm\n", encoding="utf-8")

    alg_root = test_root / "algorithms" / "alg.sorting" / "alg.min.max"
    alg_root.mkdir(parents=True)
    (alg_root / "max.pass.cpp").write_text(
        "\n".join(
            [
                "#include <cuda/std/__algorithm/max.h>",
                '#include "cuda/std/algorithm"',
                "#include <vector>",
                "// #include <cuda/std/not_real.h>",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (alg_root / "min.verify.cpp").write_text(
        "# include <cuda/std/__algorithm/min.h>\n",
        encoding="utf-8",
    )
    (alg_root / "negative.fail.cpp").write_text(
        '#include "cuda/std/__algorithm/missing.h"\n',
        encoding="utf-8",
    )
    (alg_root / "cases.h").write_text(
        "#include <cuda/std/__utility/move.h>\n",
        encoding="utf-8",
    )
    (alg_root / "notes.txt").write_text(
        "#include <cuda/std/__utility/move.h>\n",
        encoding="utf-8",
    )
    return root


def test_classify_test_kind_and_helper_header():
    assert classify_test_kind("max.pass.cpp") == "pass"
    assert classify_test_kind("empty.verify.cpp") == "verify"
    assert classify_test_kind("copy.fail.cpp") == "fail"
    assert classify_test_kind("compile.pass.cpp") == "pass"
    assert classify_test_kind("cases.h") is None
    assert is_helper_header("cases.h")
    assert is_helper_header("helper.hpp")
    assert is_helper_header("kernel.cuh")
    assert not is_helper_header("notes.txt")


def test_scan_test_index_from_fixture(tmp_path):
    cccl_root = _seed_cccl_with_tests(tmp_path)
    report = scan_test_index(cccl_root)

    tests = {entry.relative_path: entry for entry in report.tests}
    helpers = {entry.relative_path: entry for entry in report.helper_headers}
    mappings = {mapping.header: mapping for mapping in report.mappings}

    assert list(tests) == [
        "algorithms/alg.sorting/alg.min.max/max.pass.cpp",
        "algorithms/alg.sorting/alg.min.max/min.verify.cpp",
        "algorithms/alg.sorting/alg.min.max/negative.fail.cpp",
    ]
    assert list(helpers) == ["algorithms/alg.sorting/alg.min.max/cases.h"]

    max_test = tests["algorithms/alg.sorting/alg.min.max/max.pass.cpp"]
    assert max_test.kind == "pass"
    assert max_test.directory == "algorithms/alg.sorting/alg.min.max"
    assert max_test.includes == [
        "cuda/std/__algorithm/max.h",
        "cuda/std/algorithm",
    ]
    assert max_test.candidate_headers == ["__algorithm/max.h", "algorithm"]

    negative = tests["algorithms/alg.sorting/alg.min.max/negative.fail.cpp"]
    assert negative.candidate_headers == []
    assert negative.unknown_cuda_std_includes == ["cuda/std/__algorithm/missing.h"]

    helper = helpers["algorithms/alg.sorting/alg.min.max/cases.h"]
    assert helper.kind == "helper_header"
    assert helper.candidate_headers == ["__utility/move.h"]

    assert mappings["__algorithm/max.h"].tests == [
        "algorithms/alg.sorting/alg.min.max/max.pass.cpp"
    ]
    assert mappings["algorithm"].tests == ["algorithms/alg.sorting/alg.min.max/max.pass.cpp"]
    assert mappings["__algorithm/min.h"].tests == [
        "algorithms/alg.sorting/alg.min.max/min.verify.cpp"
    ]
    assert "__utility/move.h" in report.unmapped_headers
    assert report.unmapped_tests == ["algorithms/alg.sorting/alg.min.max/negative.fail.cpp"]

    summary = report.summary()
    assert summary["by_kind"] == {"fail": 1, "pass": 1, "verify": 1}
    assert summary["header_count"] == 4
    assert summary["helper_header_count"] == 1
    assert summary["mapped_header_count"] == 3
    assert summary["unmapped_header_count"] == 1
    assert summary["unmapped_test_count"] == 1


def test_write_test_index_report_is_deterministic_json(tmp_path):
    cccl_root = _seed_cccl_with_tests(tmp_path)
    report = scan_test_index(cccl_root)

    first = write_test_index_report(report, tmp_path / "outputs")
    first_text = first.read_text(encoding="utf-8")
    second = write_test_index_report(report, tmp_path / "outputs")
    second_text = second.read_text(encoding="utf-8")

    assert first == second
    assert first_text == second_text
    data = json.loads(first_text)
    assert data["summary"]["test_count"] == 3
    assert data["tests"][0]["relative_path"] == "algorithms/alg.sorting/alg.min.max/max.pass.cpp"


def test_write_test_index_report_rejects_paths_outside_outputs(tmp_path):
    cccl_root = _seed_cccl_with_tests(tmp_path)
    report = scan_test_index(cccl_root)

    with pytest.raises(ValueError):
        write_test_index_report(report, tmp_path / "outputs", filename="../outside.json")


def test_scan_test_index_rejects_missing_root(tmp_path):
    with pytest.raises(FileNotFoundError):
        scan_test_index(tmp_path / "missing")
