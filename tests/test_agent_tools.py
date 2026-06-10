"""P1 单测：模型工具层（沙箱读文件 / grep / 抽日志 / 语法自检 / dispatch）。"""

import shutil

import pytest

from core.agent_tools import AgentToolbox, parse_tool_arguments


@pytest.fixture
def toolbox(tmp_path):
    repo = tmp_path / "accl"
    inc = repo / "asc-stl" / "include" / "asc" / "std"
    inc.mkdir(parents=True)
    (inc / "__config").write_text("#define _ASC_AICORE_FN inline\n", encoding="utf-8")
    (inc / "max.h").write_text("// max header\nint sentinel_symbol = 1;\n", encoding="utf-8")
    out = tmp_path / "outputs"
    out.mkdir()
    (out / "kernel_test_x.log").write_text(
        "line ok\n" * 50 + "kernel.cpp:5:3: error: no matching function for call to 'foo'\nmore\n",
        encoding="utf-8",
    )
    return AgentToolbox(repo, out, host_include_dirs=[repo / "asc-stl" / "include"])


def test_read_repo_file_ok(toolbox):
    out = toolbox.read_repo_file("asc-stl/include/asc/std/__config")
    assert "_ASC_AICORE_FN" in out


def test_read_repo_file_missing(toolbox):
    assert "不存在" in toolbox.read_repo_file("asc-stl/include/asc/std/nope.h")


def test_read_repo_file_sandbox_escape(toolbox):
    out = toolbox.dispatch("read_repo_file", {"relpath": "../../../etc/passwd"})
    assert "越界" in out


def test_grep_repo_finds_symbol(toolbox):
    out = toolbox.grep_repo("sentinel_symbol")
    assert "max.h" in out and ":2:" in out


def test_grep_repo_no_match(toolbox):
    assert "无匹配" in toolbox.grep_repo("this_symbol_does_not_exist_xyz")


def test_extract_error_lines_from_log(toolbox):
    out = toolbox.dispatch("extract_error_lines", {"log_name": "kernel_test_x.log"})
    assert "no matching function" in out
    # 抽取后远小于原始 50+ 行噪音
    assert out.count("\n") < 20


def test_extract_error_lines_from_text(toolbox):
    out = toolbox.extract_error_lines(text="all good\nundefined reference to `bar'\nbye")
    assert "undefined reference" in out


def test_dispatch_unknown_tool(toolbox):
    assert "未知工具" in toolbox.dispatch("nope", {})


def test_dispatch_missing_arg(toolbox):
    assert "缺少必填参数" in toolbox.dispatch("read_repo_file", {})


def test_parse_tool_arguments():
    assert parse_tool_arguments('{"a": 1}') == {"a": 1}
    assert parse_tool_arguments({"a": 1}) == {"a": 1}
    assert parse_tool_arguments("not json") == {}
    assert parse_tool_arguments("") == {}


@pytest.mark.skipif(not shutil.which("g++"), reason="需要 g++ 才能做 host 语法自检")
def test_host_syntax_check_ok(toolbox):
    out = toolbox.host_syntax_check("int main() { return 0; }")
    assert out.startswith("OK")


@pytest.mark.skipif(not shutil.which("g++"), reason="需要 g++ 才能做 host 语法自检")
def test_host_syntax_check_detects_error(toolbox):
    out = toolbox.host_syntax_check("int main() { return notdeclared; }")
    assert out.startswith("FAILED")
    assert "error" in out.lower()


def test_schemas_shape():
    names = {s["function"]["name"] for s in AgentToolbox.schemas()}
    assert names == {"read_repo_file", "grep_repo", "host_syntax_check", "extract_error_lines"}
