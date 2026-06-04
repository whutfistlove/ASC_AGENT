"""operator_test 单测：生成 host/kernel 测试脚手架与命令构造。"""

from pathlib import Path

import pytest

from core.config import Config
from core.operator_test import OperatorTestRunner


def _make_config(tmp_path) -> Config:
    mylearn = tmp_path / "mylearn"
    kernel_tpl = (
        mylearn
        / "libascendcxx"
        / "test"
        / "libascendcxx"
        / "ascend"
        / "kernel"
        / "max_example"
        / "cmake"
    )
    kernel_tpl.mkdir(parents=True, exist_ok=True)
    (kernel_tpl / "npu_lib.cmake").write_text("# template\n", encoding="utf-8")

    return Config.load(
        None,
        project_root=tmp_path,
        overrides={
            "paths": {
                "mylearn_repo": str(mylearn),
                "output_dir": str(tmp_path / "outputs"),
            },
            "repo_verify": {"conda_sh": ""},
        },
    )


def test_prepare_tests_creates_host_and_kernel_scaffold(tmp_path):
    cfg = _make_config(tmp_path)
    runner = OperatorTestRunner(cfg, verbose=False, dry_run=True)

    res = runner.prepare_tests("libascendcxx/include/ascend/std/__algorithm/max.h")

    assert res.algo_name == "max"
    assert res.include_path == "ascend/std/__algorithm/max.h"
    assert Path(res.host_test_file).exists()
    assert Path(res.kernel_test_dir).exists()
    assert Path(res.kernel_test_dir, "run_test.sh").exists()
    assert Path(res.kernel_test_dir, "cmake", "npu_lib.cmake").exists()
    assert "ascend::std::max" in Path(res.host_test_file).read_text(encoding="utf-8")


def test_prepare_and_run_dry_run_records_commands_and_logs(tmp_path):
    cfg = _make_config(tmp_path)
    runner = OperatorTestRunner(cfg, verbose=False, dry_run=True)

    res = runner.prepare_and_run(
        "libascendcxx/include/ascend/std/__algorithm/min.h",
        run_host=True,
        run_kernel=True,
        kernel_mode="run_test",
    )

    assert len(res.commands) == 2
    assert res.host_ran is False
    assert res.kernel_ran is False
    assert Path(res.host_log_path).exists()
    assert Path(res.kernel_log_path).exists()


def test_include_path_requires_include_segment():
    with pytest.raises(ValueError):
        OperatorTestRunner.include_path_from_target_relpath("libascendcxx/src/foo.h")


def test_prepare_tests_with_artifacts_uses_model_host_and_kernel_spec(tmp_path):
    cfg = _make_config(tmp_path)
    runner = OperatorTestRunner(cfg, verbose=False, dry_run=True)

    host_code = (
        '#include "ascend/std/__algorithm/min.h"\n'
        "#include <iostream>\n"
        "int main() { std::cout << \"[host][min] custom\\n\"; return 0; }\n"
    )
    spec = {
        "gm_inputs": 2,
        "input_init": "h_x[i] = static_cast<float>(i); h_y[i] = static_cast<float>(i) + 1.0f;",
        "element_op_code": "z_val = ascend::std::min(x_val, y_val);",
        "golden_code": "expected = (x_ref < y_ref) ? x_ref : y_ref;",
    }

    res = runner.prepare_tests(
        "libascendcxx/include/ascend/std/__algorithm/min.h",
        host_test_code=host_code,
        kernel_spec=spec,
    )

    # host 测试就是模型产物，逐字写入（不再走写死模板）。
    assert Path(res.host_test_file).read_text(encoding="utf-8") == host_code

    kernel_dir = Path(res.kernel_test_dir)
    kernel_cpp = (kernel_dir / "kernel.cpp").read_text(encoding="utf-8")
    main_cpp = (kernel_dir / "main.cpp").read_text(encoding="utf-8")
    # kernel 用模型填的逐元素算子；golden 独立（不调用 ascend::std）。
    assert "z_val = ascend::std::min(x_val, y_val);" in kernel_cpp
    assert "expected = (x_ref < y_ref) ? x_ref : y_ref;" in main_cpp
    assert "ascend::std::min(x_ref" not in main_cpp
    # Goal 2：kernel 日志逐条采样打印的标记存在。
    assert "[kernel][min][" in main_cpp
    assert "checked " in main_cpp
    # spec 落盘，便于排查。
    assert (kernel_dir / "kernel_spec.json").exists()


def test_prepare_tests_supports_wide_kernel_io_shape(tmp_path):
    cfg = _make_config(tmp_path)
    runner = OperatorTestRunner(cfg, verbose=False, dry_run=True)

    spec = {
        "gm_inputs": 4,
        "gm_outputs": 5,
        "input_init": (
            "h_in0[i] = static_cast<float>(i); "
            "h_in1[i] = static_cast<float>(i + 1); "
            "h_in2[i] = static_cast<float>(i + 2); "
            "h_in3[i] = static_cast<float>(i + 3);"
        ),
        "element_op_code": (
            "out0_val = in0_val + in1_val; "
            "out1_val = in1_val + in2_val; "
            "out2_val = in2_val + in3_val; "
            "out3_val = in0_val - in3_val; "
            "out4_val = in0_val + in1_val + in2_val + in3_val;"
        ),
        "golden_code": (
            "expected0 = in0_ref + in1_ref; "
            "expected1 = in1_ref + in2_ref; "
            "expected2 = in2_ref + in3_ref; "
            "expected3 = in0_ref - in3_ref; "
            "expected4 = in0_ref + in1_ref + in2_ref + in3_ref;"
        ),
    }

    res = runner.prepare_tests(
        "libascendcxx/include/ascend/std/__algorithm/wide.h",
        kernel_spec=spec,
    )

    kernel_dir = Path(res.kernel_test_dir)
    host_h = (kernel_dir / "host.h").read_text(encoding="utf-8")
    kernel_cpp = (kernel_dir / "kernel.cpp").read_text(encoding="utf-8")
    main_cpp = (kernel_dir / "main.cpp").read_text(encoding="utf-8")

    assert "in3_dev" in host_h and "out4_dev" in host_h
    assert "void wide_kernel(GM_ADDR in0_gm, GM_ADDR in1_gm, GM_ADDR in2_gm, GM_ADDR in3_gm" in kernel_cpp
    assert "out4Local.SetValue(i, out4_val);" in kernel_cpp
    assert "std::vector<float> h_in3(n);" in main_cpp
    assert "std::vector<float> h_out4(n);" in main_cpp
    assert "expected4 = in0_ref + in1_ref + in2_ref + in3_ref;" in main_cpp
    assert "[out4]" in main_cpp


def test_prepare_tests_fallback_template_without_artifacts(tmp_path):
    cfg = _make_config(tmp_path)
    runner = OperatorTestRunner(cfg, verbose=False, dry_run=True)

    # 不传 artifacts -> 回退内置模板（保持离线/mock 行为）。
    res = runner.prepare_tests("libascendcxx/include/ascend/std/__algorithm/max.h")
    host_text = Path(res.host_test_file).read_text(encoding="utf-8")
    assert "ascend::std::max" in host_text


def test_kernel_fallback_is_smoke_not_self_consistent_green(tmp_path):
    """问题④：无 kernel_spec 时回退为显式 SMOKE，不再拿算子和自己比对造假绿。"""
    cfg = _make_config(tmp_path)
    runner = OperatorTestRunner(cfg, verbose=False, dry_run=True)
    res = runner.prepare_tests("libascendcxx/include/ascend/std/__algorithm/foo.h")
    main_cpp = Path(res.kernel_test_dir, "main.cpp").read_text(encoding="utf-8")
    assert "SMOKE-ONLY" in main_cpp
    # 不得出现独立 golden 比对痕迹（mismatches），也不得打印 verify 通过标记。
    assert "mismatches" not in main_cpp
    assert "verification passed" not in main_cpp


def test_kernel_spec_dtype_threads_integer_type(tmp_path):
    """问题⑤：kernel_spec.dtype=int32_t 时整条标量流水线用 int32_t，且精确相等比较。"""
    cfg = _make_config(tmp_path)
    runner = OperatorTestRunner(cfg, verbose=False, dry_run=True)
    spec = {
        "gm_inputs": 2,
        "dtype": "int32_t",
        "input_init": "h_x[i] = static_cast<int32_t>(i % 50); h_y[i] = static_cast<int32_t>((i * 3) % 50);",
        "element_op_code": "z_val = ascend::std::gcd(x_val, y_val);",
        "golden_code": "int32_t a=x_ref,b=y_ref; while(b){int32_t t=b;b=a%b;a=t;} expected = a<0?-a:a;",
    }
    res = runner.prepare_tests("libascendcxx/include/ascend/std/__numeric/gcd.h", kernel_spec=spec)
    kernel_cpp = Path(res.kernel_test_dir, "kernel.cpp").read_text(encoding="utf-8")
    main_cpp = Path(res.kernel_test_dir, "main.cpp").read_text(encoding="utf-8")
    assert "AscendC::GlobalTensor<int32_t>" in kernel_cpp
    assert "int32_t& z_val = out0_val;" in kernel_cpp
    assert "std::vector<int32_t> h_in0(n);" in main_cpp
    assert "got0 != expected0" in main_cpp     # 整型精确比较
    assert "eps" not in main_cpp               # 不用浮点容差


def test_kernel_run_test_sh_validates_cannsim_log(tmp_path):
    """问题①：run_test.sh 基于 cannsim.log 的真实数值校验判定，而非录制是否成功。"""
    cfg = _make_config(tmp_path)
    runner = OperatorTestRunner(cfg, verbose=False, dry_run=True)
    res = runner.prepare_tests("libascendcxx/include/ascend/std/__algorithm/max.h")
    sh = Path(res.kernel_test_dir, "run_test.sh").read_text(encoding="utf-8")
    assert "cannsim_*/cannsim.log" in sh
    assert 'grep -qF "Mismatch at"' in sh
    # 仅当命中独立 golden 的 verify 标记才输出 PASS。
    assert OperatorTestRunner.KERNEL_PASS_MARKER in sh
    assert "verification passed" in sh
