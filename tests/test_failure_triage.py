"""P0 止血相关单测：失败分类、过期缓存自愈、kernel 跳过判定。"""

from pathlib import Path

from core import build_env
from core.failure_triage import CODE, ENV, UNKNOWN, classify_failure


# --------------------------------------------------------------------------- #
# 失败分类器
# --------------------------------------------------------------------------- #
def test_classify_stale_cmake_cache_is_env():
    log = (
        "CMake Error: The current CMakeCache.txt directory /a/build is different "
        "than the directory /b/build where CMakeCache.txt was created."
    )
    assert classify_failure(log).kind == ENV


def test_classify_llvm_objdump_is_env():
    log = "FileNotFoundError: [Errno 2] No such file or directory: 'llvm-objdump'"
    assert classify_failure(log).kind == ENV


def test_classify_cannsim_missing_is_env():
    assert classify_failure("ERROR: cannsim command not found.").kind == ENV


def test_classify_driver_link_is_env():
    log = "/usr/bin/ld: libascend_dump.so: undefined reference to `drvHdcSessionClose'"
    assert classify_failure(log).kind == ENV


def test_classify_cann_register_link_is_env():
    log = "/usr/bin/ld: libregister.so: undefined reference to `ge::OpDesc::GetType() const'"
    assert classify_failure(log).kind == ENV


def test_classify_cann_symbol_lookup_is_env():
    log = "./ascendc_kernels_bbit: symbol lookup error: libregister.so: undefined symbol: _ZNK2ge12AscendStringltERKS0_"
    assert classify_failure(log).kind == ENV


def test_classify_no_matching_function_is_code():
    log = "kernel.cpp:56:23: error: no matching function for call to 'sort3'"
    assert classify_failure(log).kind == CODE


def test_classify_numeric_mismatch_is_code():
    assert classify_failure("Mismatch at i=3, out0, got=1 expected=2").kind == CODE


def test_code_signature_wins_over_env_when_both_present():
    # 既有真实编译错（可改），又有下游环境噪音：应判 code 以便回传模型。
    log = "error: no matching function for call to 'foo'\n... llvm-objdump ..."
    assert classify_failure(log).kind == CODE


def test_classify_empty_is_unknown():
    assert classify_failure("").kind == UNKNOWN
    assert classify_failure(None).kind == UNKNOWN


# --------------------------------------------------------------------------- #
# 过期 CMake 缓存自愈
# --------------------------------------------------------------------------- #
def test_remove_stale_cmake_cache_removes_when_path_mismatch(tmp_path):
    build = tmp_path / "build"
    build.mkdir()
    (build / "CMakeCache.txt").write_text(
        "CMAKE_CACHEFILE_DIR:INTERNAL=/old/place/build\n", encoding="utf-8"
    )
    assert build_env.remove_stale_cmake_cache(build) is True
    assert not build.exists()


def test_remove_stale_cmake_cache_keeps_when_path_matches(tmp_path):
    build = tmp_path / "build"
    build.mkdir()
    (build / "CMakeCache.txt").write_text(
        f"CMAKE_CACHEFILE_DIR:INTERNAL={build.resolve().as_posix()}\n", encoding="utf-8"
    )
    assert build_env.remove_stale_cmake_cache(build) is False
    assert build.exists()


def test_remove_stale_cmake_cache_noop_without_cache(tmp_path):
    build = tmp_path / "build"
    build.mkdir()
    assert build_env.remove_stale_cmake_cache(build) is False
