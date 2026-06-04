"""path_mapper 单测：重点验证去硬编码后的行为，以及 __cccl->__accl 段替换。"""

from pathlib import Path

import pytest

from core.path_mapper import (
    apply_segment_substitutions,
    expected_guard_from_relpath,
    infer_module_hint,
    map_cccl_test_path,
    map_target_relpath,
)

SRC = "libcudacxx/include/cuda/std"
TGT = "libascendcxx/include/ascend/std"
TEST_PREFIX = "libcudacxx/test/std"
SUBS = [{"from": "__cccl", "to": "__accl"}]


def test_module_hint_from_subdir():
    p = Path("/x/libcudacxx/include/cuda/std/__algorithm/max.h")
    assert infer_module_hint(p, SRC) == "__algorithm"


def test_module_hint_for_cccl_dir():
    # 不再有 os.h 特判：__cccl/os.h 的模块就是 __cccl
    p = Path("/x/libcudacxx/include/cuda/std/__cccl/os.h")
    assert infer_module_hint(p, SRC) == "__cccl"


def test_module_hint_file_directly_under_prefix():
    p = Path("/x/libcudacxx/include/cuda/std/version.h")
    assert infer_module_hint(p, SRC) == "version"


def test_module_hint_fallback_when_prefix_missing():
    p = Path("/somewhere/else/foo/bar.h")
    assert infer_module_hint(p, SRC, fallback="generic") == "foo"


def test_segment_substitution():
    assert apply_segment_substitutions("__cccl/os.h", SUBS) == "__accl/os.h"
    assert apply_segment_substitutions("__algorithm/max.h", SUBS) == "__algorithm/max.h"


def test_map_target_relpath_applies_substitution():
    p = Path("/x/libcudacxx/include/cuda/std/__cccl/os.h")
    rel = map_target_relpath(p, SRC, TGT, SUBS)
    assert rel == "libascendcxx/include/ascend/std/__accl/os.h"


def test_map_target_relpath_no_substitution_needed():
    p = Path("/x/libcudacxx/include/cuda/std/__algorithm/max.h")
    rel = map_target_relpath(p, SRC, TGT, SUBS)
    assert rel == "libascendcxx/include/ascend/std/__algorithm/max.h"


def test_map_target_relpath_rejects_bad_prefix():
    with pytest.raises(ValueError):
        map_target_relpath(Path("/nope/foo.h"), SRC, TGT, SUBS)


def test_guard_matches_example_os_h():
    # 这是 v2 的 bug 所在：没有段替换时 guard 会算成 ..._CCCL_OS_H_，与示例对不上。
    p = Path("/x/libcudacxx/include/cuda/std/__cccl/os.h")
    rel = map_target_relpath(p, SRC, TGT, SUBS)
    guard = expected_guard_from_relpath(rel)
    assert guard == "LIBASCENDCXX_INCLUDE_ASCEND_STD___ACCL_OS_H_"


def test_guard_matches_example_algorithm_wrapper():
    p = Path("/x/libcudacxx/include/cuda/std/__cccl/algorithm_wrapper.h")
    rel = map_target_relpath(p, SRC, TGT, SUBS)
    guard = expected_guard_from_relpath(rel)
    assert guard == "LIBASCENDCXX_INCLUDE_ASCEND_STD___ACCL_ALGORITHM_WRAPPER_H_"


def test_map_cccl_test_path_parallel_tree():
    # 算子头 -> 平行 test 树下的 .pass.cpp，子路径段保持不变。
    p = Path("/x/repos/cccl/libcudacxx/include/cuda/std/__algorithm/swap.h")
    tp = map_cccl_test_path(p, SRC, TEST_PREFIX, ".pass.cpp")
    assert tp == "/x/repos/cccl/libcudacxx/test/std/__algorithm/swap.pass.cpp"


def test_map_cccl_test_path_rejects_bad_prefix():
    with pytest.raises(ValueError):
        map_cccl_test_path(Path("/nope/foo.h"), SRC, TEST_PREFIX, ".pass.cpp")


def test_guard_without_substitution_keeps_cccl():
    # 反向验证：不传段替换则保留 __cccl（证明差异确由段替换造成）
    p = Path("/x/libcudacxx/include/cuda/std/__cccl/os.h")
    rel = map_target_relpath(p, SRC, TGT, segment_substitutions=None)
    guard = expected_guard_from_relpath(rel)
    assert guard == "LIBASCENDCXX_INCLUDE_ASCEND_STD___CCCL_OS_H_"
