"""test_migrator 单测：用 MockModelClient 锁定测试迁移的 JSON 契约（离线、无网络）。"""

import json

import pytest

import main
from core.config import Config
from core.model_client import MockModelClient
from core.test_migrator import migrate_operator_tests, validate_host_test_code, validate_kernel_spec


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


def test_validate_host_test_code_requires_nonzero_failure_exit():
    bad = (
        '#include "ascend/std/__algorithm/minmax.h"\n'
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


def test_migrate_operator_tests_parses_contract(tmp_path):
    cfg = _cfg(tmp_path)
    payload = {
        "host_test_code": (
            '#include "ascend/std/__algorithm/swap.h"\n'
            "static int g_failures = 0;\n"
            "int main(){return g_failures == 0 ? 0 : 1;}"
        ),
        "kernel_spec": {
            "gm_inputs": 2,
            "input_init": "h_x[i]=static_cast<float>(i); h_y[i]=static_cast<float>(i)+1.0f;",
            "element_op_code": "float a=x_val; float b=y_val; ascend::std::swap(a,b); z_val=a;",
            "golden_code": "expected = y_ref;",
        },
        "notes": "in-place swap",
    }
    model = MockModelClient(responses=[json.dumps(payload, ensure_ascii=False)])

    arts = migrate_operator_tests(
        cfg, model,
        algo_name="swap",
        include_path="ascend/std/__algorithm/swap.h",
        target_relpath="libascendcxx/include/ascend/std/__algorithm/swap.h",
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
    assert (cfg.output_dir / "test_migrate_result.json").exists()


def test_validate_kernel_spec_dtype_passthrough_and_normalize():
    """问题⑤：dtype 可选透传；合法整型保留，非法类型规整回退 float。"""
    base = {"input_init": "a", "element_op_code": "b", "golden_code": "c"}
    # 未给 dtype：spec 保持精简，不注入。
    out = validate_kernel_spec(dict(base))
    assert "dtype" not in out
    # 合法整型透传。
    out_i = validate_kernel_spec({**base, "dtype": "int32_t"})
    assert out_i["dtype"] == "int32_t"
    # 非法类型规整回退 float。
    out_bad = validate_kernel_spec({**base, "dtype": "weird_t"})
    assert out_bad["dtype"] == "float"
