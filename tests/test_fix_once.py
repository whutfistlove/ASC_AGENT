"""fix_once 单测：请求构造应支持可选测试反馈块。"""

from core.fix_once import build_fix_request


def test_build_fix_request_without_test_feedback():
    text = build_fix_request(
        target_relpath="libascendcxx/include/ascend/std/__algorithm/max.h",
        expected_header_guard="G_",
        baseline_text="baseline",
        commit_log_text="commit log",
    )
    assert "【最新 host/kernel 测试反馈】" not in text
    assert "commit log" in text


def test_build_fix_request_with_test_feedback():
    text = build_fix_request(
        target_relpath="libascendcxx/include/ascend/std/__algorithm/max.h",
        expected_header_guard="G_",
        baseline_text="baseline",
        commit_log_text="commit log",
        test_feedback_text="host failed at line 1",
    )
    assert "【最新 host/kernel 测试反馈】" in text
    assert "host failed at line 1" in text
