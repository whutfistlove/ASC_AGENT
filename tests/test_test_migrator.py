"""test_migrator 单测：用 MockModelClient 锁定测试迁移的 JSON 契约（离线、无网络）。"""

import json
from pathlib import Path

import pytest

import main
from core.analysis.test_index import scan_test_index
from core.common.config import Config
from core.llm.model_client import MockModelClient
from core.testing.test_migrator import (
    default_test_plan_filename,
    ensure_host_test_compiles,
    migrate_operator_tests,
    plan_upstream_tests_for_header,
    validate_host_test_code,
    validate_kernel_spec,
    write_upstream_test_plan_report,
)

_VALID_HOST = '#include "x.h"\n#include <cassert>\nint main(){ assert(1 == 1); return 0; }\n'


class _FakeToolbox:
    """最小桩：按预设序列返回 host_syntax_check 结果，记录调用。"""

    def __init__(self, results):
        self._results = list(results)
        self.calls: list[str] = []

    def host_syntax_check(self, code: str) -> str:
        self.calls.append(code)
        return self._results.pop(0)


def test_ensure_host_test_compiles_repairs_syntax_error(tmp_path):
    tb = _FakeToolbox(["FAILED：\nsnippet.cpp:30: error: expected ';' before 'int'", "OK：语法通过"])
    model = MockModelClient(responses=[json.dumps({"host_test_code": _VALID_HOST, "notes": "加分号"})])

    code, info = ensure_host_test_compiles(
        model, "int main(){} // broken", toolbox=tb,
        output_dir=tmp_path, algo_name="ctad_support", rounds=2, verbose=False,
    )

    assert info["passed"] is True
    assert info["attempts"] == 1
    assert "assert(1 == 1)" in code
    assert len(tb.calls) == 2  # 初检失败 -> 修复 -> 复检通过


def test_ensure_host_test_compiles_skips_without_compiler(tmp_path):
    tb = _FakeToolbox(["[host_syntax_check] 未找到编译器 g++，无法自检（跳过）。"])
    model = MockModelClient(responses=[])  # 不应被调用

    code, info = ensure_host_test_compiles(
        model, "orig", toolbox=tb, output_dir=tmp_path, algo_name="x", rounds=2, verbose=False,
    )

    assert info.get("no_compiler") is True
    assert code == "orig"
    assert model.calls == []


def test_ensure_host_test_compiles_noop_without_toolbox(tmp_path):
    code, info = ensure_host_test_compiles(
        MockModelClient(responses=[]), "orig", toolbox=None,
        output_dir=tmp_path, algo_name="x", rounds=2, verbose=False,
    )
    assert info["checked"] is False
    assert code == "orig"


def test_ensure_host_test_compiles_skips_repair_on_header_side_error(tmp_path):
    # 诊断指向被包含头（非 snippet.cpp）-> 测试改不了，不回灌模型，交给下游测试反馈。
    tb = _FakeToolbox(["FAILED：\nasc/std/__numeric/gcd.h:5: error: ‘foo’ was not declared"])
    model = MockModelClient(responses=[])

    code, info = ensure_host_test_compiles(
        model, "orig", toolbox=tb, output_dir=tmp_path, algo_name="x", rounds=2, verbose=False,
    )

    assert info.get("header_side") is True
    assert code == "orig"
    assert len(tb.calls) == 1
    assert model.calls == []


def _cfg(tmp_path) -> Config:
    # 用真实 project_root 让 skills/ 与 examples/tests/ 存在，仅把 output_dir 指到 tmp。
    return Config.load(
        None,
        project_root=main.PROJECT_ROOT,
        overrides={"paths": {"output_dir": str(tmp_path / "outputs")}, "repo_verify": {"conda_sh": ""}},
    )


def test_validate_kernel_spec_requires_slots():
    with pytest.raises(ValueError):
        validate_kernel_spec({"input_init": "x", "element_op_code": "y"})  # 缺 golden_code
    ok = validate_kernel_spec(
        {"input_init": "a", "element_op_code": "b", "golden_code": "c", "gm_inputs": 9, "gm_outputs": 9}
    )
    assert ok["gm_inputs"] == 2  # 超出脚手架上限时落回默认二输入
    assert ok["gm_outputs"] == 1

    wide = validate_kernel_spec(
        {"input_init": "a", "element_op_code": "b", "golden_code": "c", "gm_inputs": 4, "gm_outputs": 5}
    )
    assert wide["gm_inputs"] == 4
    assert wide["gm_outputs"] == 5
    assert wide["dtype"] == "float"


def test_validate_host_test_code_requires_nonzero_failure_exit():
    bad = (
        '#include "asc/std/__algorithm/minmax.h"\n'
        "int main(){ bool pass = false; return 0; }\n"
    )
    with pytest.raises(ValueError, match="返回非零"):
        validate_host_test_code(bad)

    with pytest.raises(ValueError, match="返回非零"):
        validate_host_test_code("int main(){ bool ok = false; return ok; }\n")

    good = (
        "static int g_failures = 0;\n"
        "int main(){ return g_failures == 0 ? 0 : 1; }\n"
    )
    assert validate_host_test_code(good).endswith("\n")
    assert validate_host_test_code("int main(){ bool ok = true; return ok ? 0 : 1; }\n").endswith("\n")


def test_validators_reject_tested_api_as_expected_or_golden():
    host = (
        '#include "asc/std/__algorithm/max.h"\n'
        "static int g_failures = 0;\n"
        "int main(){ auto expected = asc::std::max(1, 2); return g_failures ? 1 : 0; }\n"
    )
    with pytest.raises(ValueError, match="独立逻辑"):
        validate_host_test_code(host, algo_name="max")

    with pytest.raises(ValueError, match="独立 golden"):
        validate_kernel_spec(
            {
                "input_init": "h_x[i]=1; h_y[i]=2;",
                "element_op_code": "z_val = asc::std::max(x_val, y_val);",
                "golden_code": "expected = asc::std::max(x_ref, y_ref);",
            }
        )


def _seed_indexed_cccl_tests(tmp_path) -> Path:
    root = tmp_path / "cccl"
    include_root = root / "libcudacxx" / "include" / "cuda" / "std"
    test_root = root / "libcudacxx" / "test" / "libcudacxx" / "std" / "algorithms"
    (include_root / "__algorithm").mkdir(parents=True)
    (include_root / "__numeric").mkdir(parents=True)
    (include_root / "__utility").mkdir(parents=True)
    (include_root / "__algorithm" / "max.h").write_text("// max header\n", encoding="utf-8")
    (include_root / "__numeric" / "midpoint.h").write_text("// midpoint header\n", encoding="utf-8")
    (include_root / "numeric").write_text("// public numeric\n", encoding="utf-8")
    (include_root / "__utility" / "move.h").write_text("// move header\n", encoding="utf-8")
    test_root.mkdir(parents=True)
    (test_root / "max.pass.cpp").write_text(
        "#include <cuda/std/__algorithm/max.h>\nint selected_pass = 1;\n",
        encoding="utf-8",
    )
    (test_root / "max_comp.pass.cpp").write_text(
        "#include <cuda/std/__algorithm/max.h>\n#include <cuda/std/__utility/move.h>\nint blocked_pass = 1;\n",
        encoding="utf-8",
    )
    (test_root / "max_ranges.pass.cpp").write_text(
        "#include <cuda/std/__algorithm/max.h>\nint inexpressible_pass = 1;\n",
        encoding="utf-8",
    )
    (test_root / "max.verify.cpp").write_text(
        "#include <cuda/std/__algorithm/max.h>\nstatic_assert(true);\n",
        encoding="utf-8",
    )
    (test_root / "max.fail.cpp").write_text(
        "#include <cuda/std/__algorithm/max.h>\n#error compile fail\n",
        encoding="utf-8",
    )
    numeric_root = root / "libcudacxx" / "test" / "libcudacxx" / "std" / "numerics"
    numeric_root.mkdir(parents=True)
    (numeric_root / "midpoint.integer.pass.cpp").write_text(
        "#include <cuda/std/numeric>\nint midpoint_integer = 1;\n",
        encoding="utf-8",
    )
    (numeric_root / "midpoint.verify.cpp").write_text(
        "#include <cuda/std/numeric>\nstatic_assert(true);\n",
        encoding="utf-8",
    )
    return root


def test_plan_upstream_tests_selects_pass_and_defers_explicit_reasons(tmp_path):
    report = scan_test_index(_seed_indexed_cccl_tests(tmp_path))

    plan = plan_upstream_tests_for_header(
        report,
        entry_header="__algorithm/max.h",
        dependency_status_by_header={"__utility/move.h": "pending"},
        scaffold_inexpressible_tests={"algorithms/max_ranges.pass.cpp"},
    )

    assert [item.relative_path for item in plan.selected_tests] == ["algorithms/max.pass.cpp"]
    deferred = {item.relative_path: item.reason for item in plan.deferred_tests}
    assert deferred["algorithms/max_comp.pass.cpp"] == "dependency-blocked:__utility/move.h:pending"
    assert deferred["algorithms/max_ranges.pass.cpp"] == "scaffold-inexpressible"
    assert deferred["algorithms/max.verify.cpp"] == "verify-deferred"
    assert deferred["algorithms/max.fail.cpp"] == "compile-fail"
    assert "selected_pass" in plan.selected_test_text
    assert "blocked_pass" not in plan.selected_test_text


def test_plan_upstream_tests_infers_public_include_tests_for_private_header(tmp_path):
    report = scan_test_index(_seed_indexed_cccl_tests(tmp_path))

    plan = plan_upstream_tests_for_header(
        report,
        entry_header="__numeric/midpoint.h",
        dependency_status_by_header={"numeric": "pending"},
    )

    assert [item.relative_path for item in plan.selected_tests] == [
        "numerics/midpoint.integer.pass.cpp"
    ]
    assert "midpoint_integer" in plan.selected_test_text
    assert [(item.relative_path, item.reason) for item in plan.deferred_tests] == [
        ("numerics/midpoint.verify.cpp", "verify-deferred")
    ]


def test_write_upstream_test_plan_report_is_deterministic(tmp_path):
    report = scan_test_index(_seed_indexed_cccl_tests(tmp_path))
    plan = plan_upstream_tests_for_header(report, entry_header="__algorithm/max.h")

    path = write_upstream_test_plan_report(plan, tmp_path / "outputs")
    first = path.read_text(encoding="utf-8")
    second_path = write_upstream_test_plan_report(plan, tmp_path / "outputs")
    second = second_path.read_text(encoding="utf-8")

    assert path == second_path
    assert path.name == default_test_plan_filename("__algorithm/max.h")
    assert first == second
    data = json.loads(first)
    assert data["entry_header"] == "__algorithm/max.h"
    assert data["summary"]["selected_count"] == 3
    assert "selected_pass" in data["selected_test_text"]

    with pytest.raises(ValueError):
        write_upstream_test_plan_report(plan, tmp_path / "outputs", filename="../outside.json")


def test_migrate_operator_tests_parses_contract(tmp_path):
    cfg = _cfg(tmp_path)
    payload = {
        "host_test_code": (
            '#include "asc/std/__algorithm/swap.h"\n'
            "static int g_failures = 0;\n"
            "int main(){return g_failures == 0 ? 0 : 1;}"
        ),
        "kernel_spec": {
            "gm_inputs": 2,
            "input_init": "h_x[i]=static_cast<float>(i); h_y[i]=static_cast<float>(i)+1.0f;",
            "element_op_code": "float a=x_val; float b=y_val; asc::std::swap(a,b); z_val=a;",
            "golden_code": "expected = y_ref;",
        },
        "notes": "in-place swap",
    }
    model = MockModelClient(responses=[json.dumps(payload, ensure_ascii=False)])

    arts = migrate_operator_tests(
        cfg, model,
        algo_name="swap",
        include_path="asc/std/__algorithm/swap.h",
        target_relpath="asc-stl/include/asc/std/__algorithm/swap.h",
        cccl_header_text="// cccl swap header",
        accl_header_text="// accl swap header",
        cccl_test_text="// cccl swap test",
        verbose=False,
    )
    assert arts.has_host() and arts.has_kernel()
    assert arts.kernel_spec["golden_code"] == "expected = y_ref;"
    # 请求里带上了少样本示例（max 二元 + swap 原地）。
    req = model.calls[0]["user_content"]
    assert "测试迁移示例" in req and "swap" in req
    # 调试产物落盘。
    assert (cfg.model_output_dir / "test_migrate_result.json").exists()


def test_migrate_operator_tests_uses_real_test_index_plan_in_prompt(tmp_path):
    cfg = _cfg(tmp_path)
    report = scan_test_index(_seed_indexed_cccl_tests(tmp_path))
    payload = {
        "host_test_code": (
            '#include "asc/std/__algorithm/max.h"\n'
            "static int g_failures = 0;\n"
            "int main(){ int got = asc::std::max(1, 2); int expected = 2; "
            "if (got != expected) ++g_failures; return g_failures == 0 ? 0 : 1; }"
        ),
        "kernel_spec": {
            "gm_inputs": 2,
            "gm_outputs": 1,
            "dtype": "int32_t",
            "input_init": "h_x[i]=1; h_y[i]=2;",
            "element_op_code": "z_val = asc::std::max(x_val, y_val);",
            "golden_code": "expected = (x_ref < y_ref) ? y_ref : x_ref;",
        },
        "notes": "max selected from real index",
    }
    model = MockModelClient(responses=[json.dumps(payload, ensure_ascii=False)])

    arts = migrate_operator_tests(
        cfg,
        model,
        algo_name="max",
        include_path="asc/std/__algorithm/max.h",
        target_relpath="asc-stl/include/asc/std/__algorithm/max.h",
        cccl_header_text="// cccl max header",
        accl_header_text="// accl max header",
        cccl_test_text="// legacy should be replaced",
        test_index=report,
        entry_header="__algorithm/max.h",
        dependency_status_by_header={"__utility/move.h": "pending"},
        scaffold_inexpressible_tests={"algorithms/max_ranges.pass.cpp"},
        verbose=False,
    )

    assert arts.kernel_spec["dtype"] == "int32_t"
    assert arts.upstream_test_plan is not None
    assert arts.upstream_test_plan.summary()["selected_count"] == 1
    req = model.calls[0]["user_content"]
    assert "selected_upstream_pass_tests" in req
    assert "algorithms/max.pass.cpp [applicable-pass]" in req
    assert "selected_pass" in req
    assert "legacy should be replaced" not in req
    assert "max.verify.cpp [verify; verify-deferred]" in req
    assert "max.fail.cpp [fail; compile-fail]" in req
    saved = json.loads((cfg.model_output_dir / "test_migrate_result.json").read_text(encoding="utf-8"))
    assert saved["upstream_test_plan"]["selected_test_count"] == 1


def test_validate_kernel_spec_dtype_passthrough_and_normalize():
    """问题⑤：dtype 可选透传；合法整型保留，非法类型规整回退 float。"""
    base = {"input_init": "a", "element_op_code": "b", "golden_code": "c"}
    # 未给 dtype：Node 13 起显式落默认 dtype，便于审计 kernel contract。
    out = validate_kernel_spec(dict(base))
    assert out["dtype"] == "float"
    # 合法整型透传。
    out_i = validate_kernel_spec({**base, "dtype": "int32_t"})
    assert out_i["dtype"] == "int32_t"
    # 非法类型规整回退 float。
    out_bad = validate_kernel_spec({**base, "dtype": "weird_t"})
    assert out_bad["dtype"] == "float"
