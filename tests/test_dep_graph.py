"""Fixture tests for CCCL include dependency graph support."""

from __future__ import annotations

import json

import pytest

from core.analysis.dep_graph import scan_dependency_graph, write_dependency_graph_report


def _seed_cccl_headers(tmp_path):
    root = tmp_path / "cccl"
    include_root = root / "libcudacxx" / "include" / "cuda" / "std"
    (include_root / "__fixture").mkdir(parents=True)
    (include_root / "__fixture" / "a.h").write_text(
        "\n".join(
            [
                "#include <cuda/std/__fixture/b.h>",
                '#include "cuda/std/__fixture/missing.h"',
                "#include <vector>",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (include_root / "__fixture" / "b.h").write_text(
        "# include <cuda/std/__fixture/c.h>\n",
        encoding="utf-8",
    )
    (include_root / "__fixture" / "c.h").write_text("// leaf\n", encoding="utf-8")
    (include_root / "utility").write_text(
        '#include "cuda/std/__fixture/a.h"\n',
        encoding="utf-8",
    )
    return root


def _seed_cycle_headers(tmp_path):
    root = tmp_path / "cccl"
    include_root = root / "libcudacxx" / "include" / "cuda" / "std"
    (include_root / "__cycle").mkdir(parents=True)
    (include_root / "__cycle" / "x.h").write_text(
        "#include <cuda/std/__cycle/y.h>\n",
        encoding="utf-8",
    )
    (include_root / "__cycle" / "y.h").write_text(
        "#include <cuda/std/__cycle/x.h>\n",
        encoding="utf-8",
    )
    return root


def test_scan_dependency_graph_leaf_first_order_from_fixture(tmp_path):
    cccl_root = _seed_cccl_headers(tmp_path)
    report = scan_dependency_graph(cccl_root)
    graph = {entry.header: entry for entry in report.graph}

    assert graph["__fixture/a.h"].dependencies == ["__fixture/b.h"]
    assert graph["__fixture/a.h"].dependency_includes == ["cuda/std/__fixture/b.h"]
    assert graph["__fixture/a.h"].unknown_cuda_std_includes == [
        "cuda/std/__fixture/missing.h"
    ]
    assert graph["__fixture/b.h"].dependencies == ["__fixture/c.h"]
    assert graph["__fixture/c.h"].dependencies == []
    assert graph["utility"].dependencies == ["__fixture/a.h"]

    assert report.topological_order == [
        "__fixture/c.h",
        "__fixture/b.h",
        "__fixture/a.h",
        "utility",
    ]
    assert report.cycles == []
    assert report.summary()["edge_count"] == 3
    assert report.summary()["unknown_cuda_std_include_count"] == 1


def test_scan_dependency_graph_adds_symbol_dependency_edges(tmp_path):
    root = tmp_path / "cccl"
    include_root = root / "libcudacxx" / "include" / "cuda" / "std"
    (include_root / "__algorithm").mkdir(parents=True)
    (include_root / "__utility").mkdir(parents=True)
    (include_root / "__algorithm" / "swap.h").write_text(
        "_Tp tmp(_CUDA_VSTD::move(value));\n",
        encoding="utf-8",
    )
    (include_root / "__utility" / "move.h").write_text("// move\n", encoding="utf-8")

    report = scan_dependency_graph(
        root,
        symbol_dependency_rules=[
            {
                "symbol": "_CUDA_VSTD::move",
                "header": "__utility/move.h",
                "include": "cuda/std/__utility/move.h",
            }
        ],
    )
    graph = {entry.header: entry for entry in report.graph}

    swap = graph["__algorithm/swap.h"]
    assert swap.include_dependencies == []
    assert swap.symbol_dependencies == ["__utility/move.h"]
    assert swap.symbol_dependency_includes == ["cuda/std/__utility/move.h"]
    assert swap.symbol_dependency_symbols == ["_CUDA_VSTD::move"]
    assert swap.dependencies == ["__utility/move.h"]
    assert report.topological_order.index("__utility/move.h") < report.topological_order.index("__algorithm/swap.h")
    assert report.summary()["symbol_dependency_edge_count"] == 1


def test_scan_dependency_graph_reports_cycles_safely(tmp_path):
    cccl_root = _seed_cycle_headers(tmp_path)
    report = scan_dependency_graph(cccl_root)

    assert report.summary()["has_cycles"] is True
    assert report.cycles == [["__cycle/x.h", "__cycle/y.h", "__cycle/x.h"]]
    assert sorted(report.topological_order) == ["__cycle/x.h", "__cycle/y.h"]


def test_write_dependency_graph_report_is_deterministic_json(tmp_path):
    cccl_root = _seed_cccl_headers(tmp_path)
    report = scan_dependency_graph(cccl_root)

    first = write_dependency_graph_report(report, tmp_path / "outputs")
    first_text = first.read_text(encoding="utf-8")
    second = write_dependency_graph_report(report, tmp_path / "outputs")
    second_text = second.read_text(encoding="utf-8")

    assert first == second
    assert first_text == second_text
    data = json.loads(first_text)
    assert data["summary"]["header_count"] == 4
    assert data["topological_order"] == [
        "__fixture/c.h",
        "__fixture/b.h",
        "__fixture/a.h",
        "utility",
    ]


def test_write_dependency_graph_report_rejects_paths_outside_outputs(tmp_path):
    cccl_root = _seed_cccl_headers(tmp_path)
    report = scan_dependency_graph(cccl_root)

    with pytest.raises(ValueError):
        write_dependency_graph_report(report, tmp_path / "outputs", filename="../outside.json")
