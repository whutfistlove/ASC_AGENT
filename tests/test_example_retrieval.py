"""单测：few-shot 示例检索（纯词法、离线、确定性；只读 examples/）。"""

from pathlib import Path

from core.example_retrieval import (
    discover_header_pairs,
    discover_test_triples,
    select_header_examples,
    select_test_examples,
)


class _Cfg:
    """最小 config 桩：只提供检索需要的两个方法 + few_shot 旋钮。"""

    def __init__(self, examples, test_examples):
        self._e = examples
        self._t = test_examples

    def example_paths(self):
        return self._e

    def test_example_paths(self):
        return self._t


def _seed_headers(tmp_path) -> Path:
    d = tmp_path / "examples" / "headers"
    d.mkdir(parents=True)
    (d / "max.cccl.h").write_text("template max returns greater of two", encoding="utf-8")
    (d / "max.accl.h").write_text("// accl max", encoding="utf-8")
    (d / "gcd.cccl.h").write_text("numeric gcd euclid integer remainder", encoding="utf-8")
    (d / "gcd.accl.h").write_text("// accl gcd", encoding="utf-8")
    (d / "swap.cccl.h").write_text("in place swap two references void", encoding="utf-8")
    (d / "swap.accl.h").write_text("// accl swap", encoding="utf-8")
    return d


def test_discover_header_pairs(tmp_path):
    d = _seed_headers(tmp_path)
    pairs = discover_header_pairs(d)
    names = {p["name"] for p in pairs}
    assert names == {"max", "gcd", "swap"}


def test_select_header_exact_name_ranks_first(tmp_path):
    d = _seed_headers(tmp_path)
    cfg = _Cfg({"e1": {"cccl": str(d / "max.cccl.h"), "accl": str(d / "max.accl.h")}}, {})
    out = select_header_examples(
        cfg, target_relpath="libascendcxx/include/ascend/std/__numeric/gcd.h",
        source_text="whatever", k=2,
    )
    # 迁 gcd 时，gcd 示例必须排第一（同名命中）。
    assert Path(out[0][0]).name == "gcd.cccl.h"


def test_select_header_by_token_overlap_when_no_name_match(tmp_path):
    d = _seed_headers(tmp_path)
    cfg = _Cfg({"e1": {"cccl": str(d / "max.cccl.h"), "accl": str(d / "max.accl.h")}}, {})
    # 算子名 zzz 不命中任何示例；靠源文本 token 重叠：内容贴近 swap。
    out = select_header_examples(
        cfg, target_relpath="libascendcxx/include/ascend/std/__x/zzz.h",
        source_text="in place swap two references void", k=1,
    )
    assert Path(out[0][0]).name == "swap.cccl.h"


def test_select_header_disabled_keeps_configured_order(tmp_path):
    d = _seed_headers(tmp_path)
    cfg = _Cfg(
        {
            "e1": {"cccl": str(d / "max.cccl.h"), "accl": str(d / "max.accl.h")},
            "e2": {"cccl": str(d / "swap.cccl.h"), "accl": str(d / "swap.accl.h")},
        },
        {},
    )
    out = select_header_examples(
        cfg, target_relpath="x/gcd.h", source_text="x", k=2, enabled=False
    )
    assert [Path(c).name for c, _ in out] == ["max.cccl.h", "swap.cccl.h"]


def _seed_tests(tmp_path) -> Path:
    d = tmp_path / "examples" / "tests"
    d.mkdir(parents=True)
    for name in ("max", "swap"):
        (d / f"{name}.cccl.pass.cpp").write_text(f"// cccl {name} test", encoding="utf-8")
        (d / f"{name}.accl_host.cpp").write_text(f"// accl {name} host", encoding="utf-8")
        (d / f"{name}.accl_kernel_spec.json").write_text("{}", encoding="utf-8")
    return d


def test_discover_test_triples(tmp_path):
    d = _seed_tests(tmp_path)
    triples = discover_test_triples(d)
    assert {t["name"] for t in triples} == {"max", "swap"}


def test_select_header_exclude_self_drops_own_answer(tmp_path):
    d = _seed_headers(tmp_path)  # max, gcd, swap
    cfg = _Cfg({"e1": {"cccl": str(d / "max.cccl.h"), "accl": str(d / "max.accl.h")}}, {})
    # 迁 swap 且 exclude_self：swap 自己不应作为示例（防泄漏）。
    out = select_header_examples(
        cfg, target_relpath="x/swap.h", source_text="in place swap two references void",
        k=3, exclude_self=True,
    )
    assert all(Path(c).name != "swap.cccl.h" for c, _ in out)


def test_select_test_exclude_self_drops_own_answer(tmp_path):
    d = _seed_tests(tmp_path)  # max, swap
    cfg = _Cfg(
        {},
        {"e1": {"cccl_test": str(d / "max.cccl.pass.cpp"),
                "accl_host": str(d / "max.accl_host.cpp"),
                "accl_kernel_spec": str(d / "max.accl_kernel_spec.json")}},
    )
    out = select_test_examples(cfg, algo_name="swap", cccl_test_text="x", k=3, exclude_self=True)
    assert all(t["name"] != "swap" for t in out)


def test_select_test_examples_ranks_by_algo_name(tmp_path):
    d = _seed_tests(tmp_path)
    cfg = _Cfg(
        {},
        {"e1": {"cccl_test": str(d / "max.cccl.pass.cpp"),
                "accl_host": str(d / "max.accl_host.cpp"),
                "accl_kernel_spec": str(d / "max.accl_kernel_spec.json")}},
    )
    out = select_test_examples(cfg, algo_name="swap", cccl_test_text="x", k=2)
    assert out[0]["name"] == "swap"
