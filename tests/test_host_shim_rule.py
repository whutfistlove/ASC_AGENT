"""``__host_stdlib/*`` 转发垫片内容门的单元测试（纯词法、离线）。"""

from core.testing.host_shim_rule import (
    check_host_stdlib_forwarding,
    expected_system_header,
    is_host_stdlib_shim,
)

ASC_STL = "asc-stl/include/asc/std/__host_stdlib/"


def _good(name: str) -> str:
    return (
        f"#ifndef ASC_STL_INCLUDE_ASC_STD___HOST_STDLIB_{name.upper()}_\n"
        f"#define ASC_STL_INCLUDE_ASC_STD___HOST_STDLIB_{name.upper()}_\n"
        '#include "asc/std/__config"\n'
        "#if defined(__CCE__)\n"
        "#define ASC_DEVICE_CODE\n"
        "#else\n"
        f"#include <{name}>\n"
        "#endif\n"
        "#endif\n"
    )


def _empty_stub(name: str) -> str:
    return (
        f"#ifndef G_{name.upper()}\n#define G_{name.upper()}\n"
        '#include "asc/std/__config"\n'
        "#if defined(__CCE__)\n#define ASC_DEVICE_CODE\n#endif\n"
        "// host include dropped -> 空壳\n"
        "#endif\n"
    )


def test_module_detection_and_header_name():
    assert is_host_stdlib_shim(ASC_STL + "algorithm")
    assert not is_host_stdlib_shim("asc-stl/include/asc/std/__algorithm/all_of.h")
    assert expected_system_header(ASC_STL + "algorithm") == "algorithm"
    assert expected_system_header(ASC_STL + "math.h") == "math.h"


def test_non_shim_is_not_applicable():
    res = check_host_stdlib_forwarding(
        "asc-stl/include/asc/std/__algorithm/all_of.h", "whatever"
    )
    assert res.applicable is False
    assert res.ok is True


def test_good_shim_passes():
    for name in ("algorithm", "numeric", "memory", "stdexcept"):
        res = check_host_stdlib_forwarding(ASC_STL + name, _good(name))
        assert res.applicable and res.ok, name


def test_extensioned_system_header_passes():
    res = check_host_stdlib_forwarding(ASC_STL + "math.h", _good("math.h"))
    assert res.applicable and res.ok


def test_empty_stub_fails():
    # 这正是 __host_stdlib/algorithm 曾经的回归形态。
    res = check_host_stdlib_forwarding(ASC_STL + "algorithm", _empty_stub("algorithm"))
    assert res.applicable is True
    assert res.ok is False
    assert "algorithm" in res.reason


def test_commented_out_include_does_not_count():
    body = (
        "#ifndef G\n#define G\n"
        "#if defined(__CCE__)\n#define ASC_DEVICE_CODE\n#else\n"
        "// #include <algorithm>\n"
        "/* #include <algorithm> */\n"
        "#endif\n#endif\n"
    )
    res = check_host_stdlib_forwarding(ASC_STL + "algorithm", body)
    assert res.ok is False


def test_include_with_trailing_comment_counts():
    body = (
        "#ifndef G\n#define G\n"
        "#if defined(__CCE__)\n#define ASC_DEVICE_CODE\n#else\n"
        "#include <numeric>   // host fallback\n"
        "#endif\n#endif\n"
    )
    res = check_host_stdlib_forwarding(ASC_STL + "numeric", body)
    assert res.ok is True
