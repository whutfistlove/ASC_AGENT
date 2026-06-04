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
