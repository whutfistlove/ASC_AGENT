"""脚手架统一化单测：host/kernel/full 三个生成脚本共用同一 env 片段，且保留关键步骤。"""

from core import scaffold_scripts as K
from core.operator_kernel_scaffold import KERNEL_CANNSIM_SOC_VERSION
from core.scaffold_env import env_setup_block

ENV_MARK = "core/scaffold_env.py 生成"


def test_env_block_is_single_source():
    env = env_setup_block()
    assert 'if [ -z "$ASCEND_HOME_PATH" ]' not in env
    assert "$ASCEND_HOME_PATH/devlib" in env
    assert "/usr/local/Ascend/driver/lib64" in env
    assert 'LD_LIBRARY_PATH="${LD_LIBRARY_PATH:+$LD_LIBRARY_PATH:}$__d"' in env
    # 三个脚本都嵌入同一份 env 片段（单一事实源）。
    for sh in (K.run_test_sh("max"), K.host_run_test_sh("max"), K.full_project_run_sh("max")):
        assert ENV_MARK in sh
        assert "conda activate" in sh or "source activate" in sh
        assert "set_env.sh" in sh


def test_host_script_targets_only_that_algo():
    sh = K.host_run_test_sh("clamp")
    assert "make clamp_host_test" in sh
    assert "ctest -R \"host\\.clamp$\"" in sh
    assert "CMAKE_EXPORT_COMPILE_COMMANDS" in sh
    # 含过期缓存守卫（手动运行也健壮）
    assert "stale CMake cache" in sh


def test_full_project_script_builds_and_filters():
    sh = K.full_project_run_sh("minmax")
    assert "BUILD_TESTING=ON" in sh
    assert "ctest -R \"kernel\\.minmax\\.sim$\"" in sh


def test_kernel_run_test_preserves_pass_judgment():
    sh = K.run_test_sh("sort3")
    # 统一 env 后，cannsim.log 的真实数值判定逻辑必须保留。
    assert f"cannsim record ./ascendc_kernels_bbit -s {KERNEL_CANNSIM_SOC_VERSION}" in sh
    assert 'tail -n 200 "$SIM_LOG"' in sh
    assert "KERNEL_SIM_RESULT: PASS" in sh
    assert "Mismatch at" in sh


def test_kernel_run_test_uses_configurable_cannsim_soc():
    sh = K.run_test_sh("sort3", cannsim_soc_version="AscendCustom")
    assert "cannsim record ./ascendc_kernels_bbit -s AscendCustom" in sh


def test_scripts_have_shebang_and_set_e():
    for sh in (K.run_test_sh("a"), K.host_run_test_sh("a"), K.full_project_run_sh("a")):
        assert sh.startswith("#!/bin/bash")
        assert "set -e" in sh
