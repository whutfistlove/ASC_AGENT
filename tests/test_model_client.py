"""model_client 单测：JSON 解析、归一化、Mock 客户端。"""

import json

import pytest

from core.llm.model_client import (
    MockModelClient,
    extract_json_object,
    normalize_generated_text,
)


def test_extract_plain_json():
    assert extract_json_object('{"a": 1}') == {"a": 1}


def test_extract_fenced_json():
    text = "```json\n{\"a\": 1}\n```"
    assert extract_json_object(text) == {"a": 1}


def test_extract_json_with_surrounding_text():
    text = "前面一些说明\n{\"k\": \"v\"}\n后面一些说明"
    assert extract_json_object(text) == {"k": "v"}


def test_extract_json_strict_rejects_surrounding_text():
    text = "前面一些说明\n{\"k\": \"v\"}"
    with pytest.raises(ValueError, match="单个 JSON 对象"):
        extract_json_object(text, strict=True)


def test_extract_json_strict_rejects_fenced_json():
    text = "```json\n{\"a\": 1}\n```"
    with pytest.raises(ValueError, match="单个 JSON 对象"):
        extract_json_object(text, strict=True)


def test_extract_json_invalid_raises():
    with pytest.raises(ValueError):
        extract_json_object("no json here")


def test_normalize_directive_spacing():
    src = "#  define X 1\n#   endif\n#  include <a>\n"
    out = normalize_generated_text(src)
    assert "#define X 1" in out
    assert "#endif" in out
    assert "#include <a>" in out


def test_normalize_trailing_newline():
    assert normalize_generated_text("abc").endswith("\n")
    assert not normalize_generated_text("abc").endswith("\n\n")


def test_normalize_respects_options_off():
    src = "#  define X 1"
    out = normalize_generated_text(src, {"fix_directive_spacing": False, "ensure_trailing_newline": False})
    assert out == "#  define X 1"


def test_mock_scripted_responses_in_order():
    client = MockModelClient(responses=['{"a":1}', '{"b":2}'])
    assert client.generate(system_prompt="s", user_content="u1") == '{"a":1}'
    assert client.generate(system_prompt="s", user_content="u2") == '{"b":2}'
    assert len(client.calls) == 2


def test_mock_scripted_exhausted_raises():
    client = MockModelClient(responses=['{"a":1}'])
    client.generate(system_prompt="s", user_content="u")
    with pytest.raises(AssertionError):
        client.generate(system_prompt="s", user_content="u")


def test_mock_auto_uses_expected_guard():
    client = MockModelClient()
    req = "【expected_header_guard】\nASC_STL_INCLUDE_ASC_STD___ASC_OS_H_\n\n其它"
    raw = client.generate(system_prompt="s", user_content=req)
    data = json.loads(raw)
    assert "ASC_STL_INCLUDE_ASC_STD___ASC_OS_H_" in data["rewritten_code"]
    assert data["file_type"] == "mock_header"
