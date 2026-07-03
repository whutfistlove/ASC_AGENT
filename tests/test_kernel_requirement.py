"""kernel 适用性分类器单测：判断头需不需要 kernel 侧测试。"""

from __future__ import annotations

import json
from pathlib import Path

from core.llm.model_client import MockModelClient
from core.testing.kernel_requirement import (
    HOST_ONLY,
    KERNEL_APPLICABLE,
    UNKNOWN,
    classify_kernel_requirement,
    decide_kernel_requirement,
    module_of,
    needs_kernel_test,
)

_DEVICE_FN = "_CCCL_API constexpr const _Tp& clamp(const _Tp& __v) { return __v; }\n"
_TRAIT = "template <class T> struct is_foo { static constexpr bool value = true; };\n"


class _JudgeConfig:
    def __init__(self, root: Path):
        self.model_output_dir = root

    @staticmethod
    def read_skill(name: str) -> str:
        assert name == "judge_kernel_requirement.md"
        return "Return strict JSON."


def test_host_only_modules_take_precedence_over_device_function():
    # 含 constexpr 辅助函数的 type_trait（命中设备函数正则）仍按模块判为 host_only。
    assert classify_kernel_requirement("__type_traits/is_foo.h", _DEVICE_FN) == HOST_ONLY
    assert classify_kernel_requirement("__host_stdlib/algorithm", "#include <algorithm>\n") == HOST_ONLY
    assert classify_kernel_requirement("__fwd/array.h", "template <class> struct array;\n") == HOST_ONLY
    assert classify_kernel_requirement("__concepts/x.h", "#define _CCCL_CONCEPT(x)\n") == HOST_ONLY


def test_device_function_marks_kernel_applicable():
    assert classify_kernel_requirement("__algorithm/clamp.h", _DEVICE_FN) == KERNEL_APPLICABLE
    assert classify_kernel_requirement("__numeric/gcd.h", "_CCCL_HOST_DEVICE int gcd(int a){return a;}") == KERNEL_APPLICABLE


def test_trait_only_content_in_other_module_is_host_only():
    assert classify_kernel_requirement("__other/bar.h", _TRAIT) == HOST_ONLY


def test_ctad_support_header_is_host_only():
    # __utility/ctad_support.h：只产出 CTAD 推导指引，纯编译期，无设备算子 -> host_only。
    ctad = (
        "#define _ASC_CTAD_SUPPORTED_FOR_TYPE(_ClassName) \\\n"
        "  template <class... _Tag>                        \\\n"
        "  _ClassName(typename _Tag::__allow_ctad...)->_ClassName<_Tag...>\n"
    )
    assert classify_kernel_requirement("__utility/ctad_support.h", ctad) == HOST_ONLY
    assert needs_kernel_test("__utility/ctad_support.h", ctad) is False


def test_macro_only_header_is_host_only():
    macro_only = "#ifndef X\n#define X\n#include <foo>\n#define FOO(a) ((a) + 1)\n#endif\n"
    assert classify_kernel_requirement("__other/macros.h", macro_only) == HOST_ONLY


def test_ctad_guide_does_not_override_real_device_operator():
    # 既有设备算子又有 CTAD 指引（如 operations.h 的 plus）-> 仍需 kernel。
    mixed = (
        "template <class T> struct plus {\n"
        "  _CCCL_API constexpr T operator()(const T& a, const T& b) const { return a + b; }\n"
        "};\n"
        "_CCCL_CTAD_SUPPORTED_FOR_TYPE(plus);\n"
    )
    assert classify_kernel_requirement("__functional/operations.h", mixed) == KERNEL_APPLICABLE


def test_ambiguous_content_is_unknown_and_runs_kernel():
    # 有真实代码但既非设备函数也非 trait/ctad/纯宏 → unknown → 保守跑 kernel。
    text = "namespace asc { struct bar; using foo = int; }\n"
    assert classify_kernel_requirement("__other/baz.h", text) == UNKNOWN
    assert needs_kernel_test("__other/baz.h", text) is True


def test_empty_or_missing_header_is_unknown_not_macro_only():
    # 空/缺失内容不应被当成纯宏头（否则缺目标头会误跳过 kernel）。
    assert classify_kernel_requirement("__algorithm/clamp.h", "") == UNKNOWN
    assert needs_kernel_test("__algorithm/clamp.h", "") is True


def test_needs_kernel_test_wrapper():
    assert needs_kernel_test("__type_traits/is_foo.h", _DEVICE_FN) is False
    assert needs_kernel_test("__algorithm/clamp.h", _DEVICE_FN) is True


def test_comment_keywords_do_not_trigger_device_signal():
    # 注释里的 _CCCL_API 不应被当成设备函数（剥离注释后再匹配）。
    text = "// uses _CCCL_API clamp() internally\ntemplate <class T> struct t { static constexpr bool value = false; };\n"
    assert classify_kernel_requirement("__other/c.h", text) == HOST_ONLY


def test_module_of_handles_layered_and_target_keys():
    assert module_of("__type_traits/foo.h") == "__type_traits"
    assert module_of("std/__type_traits/foo.h") == "__type_traits"
    assert module_of("asc-stl/include/asc/std/__algorithm/max.h") == "__algorithm"


def test_host_only_modules_override():
    # 自定义 host-only 模块集：把 __algorithm 也当 host-only。
    assert classify_kernel_requirement(
        "__algorithm/clamp.h", _DEVICE_FN, host_only_modules=frozenset({"__algorithm"})
    ) == HOST_ONLY


def _judge(tmp_path, source: str, payload: dict | str | None):
    model = None
    if payload is not None:
        raw = payload if isinstance(payload, str) else json.dumps(payload)
        model = MockModelClient(responses=[raw])
    return decide_kernel_requirement(
        config=_JudgeConfig(tmp_path),
        model_client=model,
        relpath="__type_traits/is_foo.h" if "value" in source else "__algorithm/clamp.h",
        source_text=source,
    )


def test_rule_and_model_host_only_agreement_skips_kernel(tmp_path):
    decision = _judge(tmp_path, _TRAIT, {
        "classification": "host_only",
        "needs_kernel_test": False,
        "reason": "compile-time trait only",
        "evidence": ["static constexpr value"],
    })
    assert decision.agreement is True
    assert decision.needs_kernel_test is False
    assert decision.resolution == "agreement"


def test_rule_model_disagreement_requires_kernel(tmp_path):
    decision = _judge(tmp_path, _TRAIT, {
        "classification": "kernel_applicable",
        "needs_kernel_test": True,
        "reason": "model chooses device validation",
        "evidence": [],
    })
    assert decision.agreement is False
    assert decision.needs_kernel_test is True
    assert decision.resolution == "disagreement_requires_kernel"


def test_model_host_only_cannot_downgrade_rule_required_kernel(tmp_path):
    decision = _judge(tmp_path, _DEVICE_FN, {
        "classification": "host_only",
        "needs_kernel_test": False,
        "reason": "incorrect model downgrade",
        "evidence": [],
    })
    assert decision.rule_needs_kernel_test is True
    assert decision.needs_kernel_test is True
    assert decision.resolution == "disagreement_requires_kernel"


def test_invalid_or_unavailable_model_requires_kernel(tmp_path):
    invalid = _judge(tmp_path, _TRAIT, '{"needs_kernel_test": "false"}')
    assert invalid.model_status == "error"
    assert invalid.needs_kernel_test is True
    unavailable = _judge(tmp_path, _TRAIT, None)
    assert unavailable.model_status == "unavailable"
    assert unavailable.needs_kernel_test is True
    result_files = list(tmp_path.glob("kernel_requirement_result_*.json"))
    assert result_files
    saved = json.loads(result_files[0].read_text(encoding="utf-8"))
    assert saved["resolution"] == "model_unavailable_requires_kernel"
