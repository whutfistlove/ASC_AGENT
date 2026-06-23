"""Tests for ACCL target header inventory support."""

from __future__ import annotations

from core.analysis.target_inventory import (
    asc_include_to_std_relpath,
    parse_asc_std_includes,
    scan_target_header_inventory,
)


def test_parse_asc_std_includes_filters_and_sorts_unique():
    text = (
        '#include "asc/std/__utility/move.h"\n'
        "#include <asc/std/__algorithm/swap.h>\n"
        '#include "asc/std/__utility/move.h"\n'
        "// #include <asc/std/ignored.h>\n"
        "#include <vector>\n"
    )

    assert parse_asc_std_includes(text) == [
        "asc/std/__algorithm/swap.h",
        "asc/std/__utility/move.h",
    ]


def test_asc_include_to_std_relpath():
    assert asc_include_to_std_relpath("asc/std/__utility/move.h") == "__utility/move.h"
    assert asc_include_to_std_relpath("cuda/std/__utility/move.h") is None


def test_scan_target_header_inventory_reports_missing_includes(tmp_path):
    target = tmp_path / "accl"
    root = target / "asc-stl" / "include" / "asc" / "std"
    (root / "__algorithm").mkdir(parents=True)
    (root / "__utility").mkdir(parents=True)
    (root / "__algorithm" / "swap.h").write_text(
        '#include "asc/std/__utility/move.h"\n'
        '#include "asc/std/__utility/missing.h"\n',
        encoding="utf-8",
    )
    (root / "__utility" / "move.h").write_text("// move\n", encoding="utf-8")

    report = scan_target_header_inventory(target)
    by_header = {entry.std_relpath: entry for entry in report.headers}

    assert by_header["__algorithm/swap.h"].dependencies == ["__utility/move.h"]
    assert by_header["__algorithm/swap.h"].missing_include_dependencies == ["__utility/missing.h"]
    assert report.summary() == {
        "broken_header_count": 1,
        "header_count": 2,
        "missing_include_count": 1,
    }
