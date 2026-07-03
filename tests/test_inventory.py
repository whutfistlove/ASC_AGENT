"""Fixture tests for real CCCL header inventory support."""

from __future__ import annotations

import json

import pytest

from core.analysis.inventory import (
    DEFAULT_CCCL_REPO,
    classify_header_shape,
    include_to_header_relpath,
    infer_header_module,
    parse_cuda_std_includes,
    resolve_cccl_repo,
    scan_header_inventory,
    scan_implicit_dependencies,
    scan_symbol_dependencies,
    write_inventory_report,
)


def _seed_cccl_headers(tmp_path):
    root = tmp_path / "cccl"
    include_root = root / "libcudacxx" / "include" / "cuda" / "std"
    (include_root / "__algorithm").mkdir(parents=True)
    (include_root / "__utility").mkdir(parents=True)
    (include_root / "__algorithm" / "max.h").write_text(
        "\n".join(
            [
                "#include <cuda/std/__config>",
                '#include "cuda/std/__utility/move.h"',
                "#include <vector>",
                "// #include <cuda/std/ignored.h>",
                "# include <cuda/std/__algorithm/comp.h>",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (include_root / "__utility" / "move.h").write_text(
        "#include <cuda/std/__config>\n",
        encoding="utf-8",
    )
    (include_root / "__config").write_text("// config\n", encoding="utf-8")
    (include_root / "algorithm").write_text(
        "#include <cuda/std/__algorithm/max.h>\n",
        encoding="utf-8",
    )
    return root


def test_resolve_cccl_repo_precedence(tmp_path):
    explicit = tmp_path / "explicit"
    env_repo = tmp_path / "env"
    assert resolve_cccl_repo(explicit, env={"CCCL_REPO": str(env_repo)}) == explicit.resolve()
    assert resolve_cccl_repo(env={"CCCL_REPO": str(env_repo)}) == env_repo.resolve()
    assert resolve_cccl_repo(env={}) == DEFAULT_CCCL_REPO.resolve()


def test_parse_cuda_std_includes_filters_and_sorts_unique():
    text = (
        "#include <cuda/std/__utility/move.h>\n"
        '#include "cuda/std/__algorithm/max.h"\n'
        "#include <cuda/std/__utility/move.h>\n"
        "#include <string>\n"
        "// #include <cuda/std/not_real.h>\n"
    )
    assert parse_cuda_std_includes(text) == [
        "cuda/std/__algorithm/max.h",
        "cuda/std/__utility/move.h",
    ]


def test_scan_symbol_dependencies_ignores_comments_and_literals():
    text = (
        "// _CUDA_VSTD::move(commented)\n"
        'const char* s = "_CUDA_VSTD::move(string)";\n'
        "auto x = _CUDA_VSTD::move(value);\n"
    )
    hits = scan_symbol_dependencies(
        text,
        [{"symbol": "_CUDA_VSTD::move", "header": "__utility/move.h", "include": "cuda/std/__utility/move.h"}],
    )

    assert [hit.symbol for hit in hits] == ["_CUDA_VSTD::move"]
    assert [hit.include for hit in hits] == ["cuda/std/__utility/move.h"]


def test_scan_symbol_dependencies_uses_identifier_boundaries():
    hits = scan_symbol_dependencies(
        "auto x = _CUDA_VSTD::move_if_noexcept(value);\n",
        [{"symbol": "_CUDA_VSTD::move", "header": "__utility/move.h", "include": "cuda/std/__utility/move.h"}],
    )

    assert hits == []


def test_generic_qualified_symbol_rule_resolves_provider_from_header_index():
    rule = {
        "pattern": r"(?:_CUDA_VSTD|(?:::)?cuda::std)::(?P<symbol>[A-Za-z_]\w*)",
        "resolver": "header_stem",
        "symbol_group": "symbol",
        "prefix_fallback": True,
        "provider_modules": ["__utility"],
    }
    known = ["__utility/move.h", "__utility/forward.h", "__algorithm/move.h"]
    hits = scan_implicit_dependencies(
        "auto a = ::cuda::std::move_if_noexcept(x); auto b = cuda::std::forward<T>(x);",
        [rule],
        known_headers=known,
    )

    assert [(hit.symbol, hit.header) for hit in hits] == [
        ("cuda::std::forward", "__utility/forward.h"),
        ("::cuda::std::move_if_noexcept", "__utility/move.h"),
    ]


def test_generic_dependency_rule_does_not_create_self_edge():
    rule = {
        "pattern": r"_CUDA_VSTD::(?P<symbol>[A-Za-z_]\w*)",
        "resolver": "header_stem",
    }
    hits = scan_implicit_dependencies(
        "return _CUDA_VSTD::move(x);",
        [rule],
        known_headers=["__utility/move.h"],
        current_header="__utility/move.h",
    )
    assert hits == []


def test_include_to_header_relpath():
    assert include_to_header_relpath("cuda/std/__algorithm/max.h") == "__algorithm/max.h"
    assert include_to_header_relpath("vector") is None


def test_module_and_shape_inference():
    assert infer_header_module("__algorithm/max.h") == "__algorithm"
    assert infer_header_module("algorithm") == "algorithm"
    assert classify_header_shape("__algorithm/max.h") == "private"
    assert classify_header_shape("__config") == "private"
    assert classify_header_shape("algorithm") == "public"


def test_scan_header_inventory_from_fixture(tmp_path):
    cccl_root = _seed_cccl_headers(tmp_path)
    report = scan_header_inventory(cccl_root)
    headers = {h.relative_path: h for h in report.headers}

    assert list(headers) == ["__algorithm/max.h", "__config", "__utility/move.h", "algorithm"]
    assert headers["__algorithm/max.h"].module == "__algorithm"
    assert headers["__algorithm/max.h"].filename == "max.h"
    assert headers["__algorithm/max.h"].shape == "private"
    assert headers["__algorithm/max.h"].includes == [
        "cuda/std/__algorithm/comp.h",
        "cuda/std/__config",
        "cuda/std/__utility/move.h",
    ]
    assert headers["algorithm"].shape == "public"
    assert report.summary()["header_count"] == 4
    assert report.summary()["by_shape"] == {"private": 3, "public": 1}


def test_scan_header_inventory_records_symbol_dependencies(tmp_path):
    cccl_root = _seed_cccl_headers(tmp_path)
    report = scan_header_inventory(
        cccl_root,
        symbol_dependency_rules=[
            {"symbol": "_CUDA_VSTD::move", "header": "__utility/move.h", "include": "cuda/std/__utility/move.h"}
        ],
    )
    headers = {h.relative_path: h for h in report.headers}

    assert headers["__algorithm/max.h"].symbol_dependencies == []

    move_path = cccl_root / "libcudacxx" / "include" / "cuda" / "std" / "__algorithm" / "uses_move.h"
    move_path.write_text("_Tp tmp(_CUDA_VSTD::move(value));\n", encoding="utf-8")
    report = scan_header_inventory(
        cccl_root,
        symbol_dependency_rules=[
            {"symbol": "_CUDA_VSTD::move", "header": "__utility/move.h", "include": "cuda/std/__utility/move.h"}
        ],
    )
    headers = {h.relative_path: h for h in report.headers}
    assert headers["__algorithm/uses_move.h"].symbol_dependencies == ["cuda/std/__utility/move.h"]


def test_write_inventory_report_is_deterministic_json(tmp_path):
    cccl_root = _seed_cccl_headers(tmp_path)
    report = scan_header_inventory(cccl_root)

    first = write_inventory_report(report, tmp_path / "outputs")
    first_text = first.read_text(encoding="utf-8")
    second = write_inventory_report(report, tmp_path / "outputs")
    second_text = second.read_text(encoding="utf-8")

    assert first == second
    assert first_text == second_text
    data = json.loads(first_text)
    assert data["headers"][0]["relative_path"] == "__algorithm/max.h"
    assert data["summary"]["header_count"] == 4


def test_write_inventory_report_rejects_paths_outside_outputs(tmp_path):
    cccl_root = _seed_cccl_headers(tmp_path)
    report = scan_header_inventory(cccl_root)

    with pytest.raises(ValueError):
        write_inventory_report(report, tmp_path / "outputs", filename="../outside.json")


def test_scan_header_inventory_rejects_missing_root(tmp_path):
    with pytest.raises(FileNotFoundError):
        scan_header_inventory(tmp_path / "missing")
