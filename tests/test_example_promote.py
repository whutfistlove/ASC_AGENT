"""单测：把已验证迁移产物晋升为 examples/ 金标准示例（含质量门禁）。"""

import json
from pathlib import Path

import pytest

from core.config import Config
from core.example_promote import discover_promotable, promote_operator, resolve_artifacts

_VALID_HOST = (
    '#include "asc/std/__algorithm/foo.h"\n'
    "static int g_failures = 0;\n"
    "int main(){ if (asc::std::foo(1) != 1) ++g_failures; return g_failures == 0 ? 0 : 1; }\n"
)
_VALID_SPEC = {
    "gm_inputs": 1,
    "input_init": "h_x[i] = static_cast<float>(i);",
    "element_op_code": "z_val = asc::std::foo(x_val);",
    "golden_code": "expected = x_ref;",
}
_VALID_ASC_HEADER = (
    "#ifndef ASC_STL_INCLUDE_ASC_STD___ALGORITHM_FOO_H_\n"
    "#define ASC_STL_INCLUDE_ASC_STD___ALGORITHM_FOO_H_\n"
    "_ASC_STD_BEGIN\n"
    "template <class T> _ASC_AICORE_FN constexpr T foo(T x){ return x; }\n"
    "_ASC_STD_END\n"
    "#endif\n"
)


def _make_project(tmp_path, *, host=_VALID_HOST, spec=_VALID_SPEC,
                  accl_header=_VALID_ASC_HEADER, with_test=True) -> Config:
    cccl = tmp_path / "repos" / "cccl"
    accl = tmp_path / "repos" / "accl"
    (cccl / "libcudacxx/include/cuda/std/__algorithm").mkdir(parents=True)
    (cccl / "libcudacxx/include/cuda/std/__algorithm/foo.h").write_text("// cccl foo\n", encoding="utf-8")
    (accl / "asc-stl/include/asc/std/__algorithm").mkdir(parents=True)
    (accl / "asc-stl/include/asc/std/__algorithm/foo.h").write_text(accl_header, encoding="utf-8")
    (tmp_path / "examples" / "headers").mkdir(parents=True)
    (tmp_path / "examples" / "tests").mkdir(parents=True)
    if with_test:
        (cccl / "libcudacxx/test/libcudacxx/std/__algorithm").mkdir(parents=True)
        (cccl / "libcudacxx/test/libcudacxx/std/__algorithm/foo.pass.cpp").write_text("// cccl foo test\n", encoding="utf-8")
        host_dir = accl / "asc-stl/test/asc-stl/asc/host"
        host_dir.mkdir(parents=True)
        (host_dir / "foo_tests.cpp").write_text(host, encoding="utf-8")
        kdir = accl / "asc-stl/test/asc-stl/asc/kernel/foo_example"
        kdir.mkdir(parents=True)
        (kdir / "kernel_spec.json").write_text(json.dumps(spec), encoding="utf-8")
    return Config.load(
        None, project_root=tmp_path,
        overrides={"paths": {"cccl_repo": str(cccl), "accl_repo": str(accl),
                             "output_dir": str(tmp_path / "outputs")},
                   "repo_verify": {"conda_sh": ""}},
    )


def test_resolve_artifacts_infers_module(tmp_path):
    cfg = _make_project(tmp_path)
    art = resolve_artifacts(cfg, "foo")
    assert art.module == "__algorithm"
    assert art.has_header_pair() and art.has_test_set()


def test_discover_promotable_lists_foo(tmp_path):
    cfg = _make_project(tmp_path)
    assert discover_promotable(cfg) == ["foo"]


def test_promote_writes_header_and_test(tmp_path):
    cfg = _make_project(tmp_path)
    r = promote_operator(cfg, "foo")
    assert r["header_written"] and r["test_written"]
    hd = tmp_path / "examples" / "headers"
    td = tmp_path / "examples" / "tests"
    assert (hd / "foo.cccl.h").exists() and (hd / "foo.accl.h").exists()
    assert (td / "foo.cccl.pass.cpp").exists()
    assert (td / "foo.accl_host.cpp").read_text(encoding="utf-8") == _VALID_HOST
    # kernel_spec 经 validate 规整后落盘（gm_outputs 补全为 1）。
    spec = json.loads((td / "foo.accl_kernel_spec.json").read_text(encoding="utf-8"))
    assert spec["gm_inputs"] == 1 and spec["gm_outputs"] == 1


def test_promote_skips_existing_without_overwrite(tmp_path):
    cfg = _make_project(tmp_path)
    promote_operator(cfg, "foo")
    r2 = promote_operator(cfg, "foo")
    assert r2["header_written"] is False and r2["test_written"] is False
    assert r2["skipped"]


def test_promote_overwrite_updates(tmp_path):
    cfg = _make_project(tmp_path)
    promote_operator(cfg, "foo")
    new_header = _VALID_ASC_HEADER.replace("return x;", "return x + T(0);")
    (Path(cfg.accl_repo) / "asc-stl/include/asc/std/__algorithm/foo.h").write_text(
        new_header, encoding="utf-8"
    )
    promote_operator(cfg, "foo", overwrite=True)
    assert "T(0)" in (tmp_path / "examples" / "headers" / "foo.accl.h").read_text(encoding="utf-8")


def test_promote_headers_only(tmp_path):
    cfg = _make_project(tmp_path)
    r = promote_operator(cfg, "foo", include_test=False)
    assert r["header_written"] and r["test_written"] is False
    assert not (tmp_path / "examples" / "tests" / "foo.cccl.pass.cpp").exists()


def test_quality_gate_rejects_header_without_guard(tmp_path):
    cfg = _make_project(tmp_path, accl_header="// no guard here\n")
    with pytest.raises(ValueError, match="guard"):
        promote_operator(cfg, "foo")


def test_quality_gate_skips_bad_host_test_but_keeps_header(tmp_path):
    # 「假绿」host 测试（永远 return 0）应被拦在库外；但有效的头仍照常晋升。
    bad_host = '#include "asc/std/__algorithm/foo.h"\nint main(){ bool ok=false; return 0; }\n'
    cfg = _make_project(tmp_path, host=bad_host)
    r = promote_operator(cfg, "foo")
    assert r["header_written"] is True
    assert r["test_written"] is False
    assert any("质量门禁" in s for s in r["skipped"])
    assert not (tmp_path / "examples" / "tests" / "foo.accl_host.cpp").exists()


def test_missing_accl_header_raises(tmp_path):
    cfg = _make_project(tmp_path)
    with pytest.raises(FileNotFoundError):
        promote_operator(cfg, "does_not_exist")
