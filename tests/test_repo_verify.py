"""repo_verify 单测：可配置 check 匹配、命令构造（dry-run）、安全转义。"""

from pathlib import Path

from core.common.config import Config
from core.repo.repo_verify import (
    RepoVerifier,
    build_branch_name,
    build_commit_message,
    check_commit_passed,
    required_checks_passed,
)

CHECKS = [
    {"name": "license", "pattern": r"Add Apache 2\.0 license header.*Passed", "required": True},
    {"name": "style", "pattern": r"CANN code style check \(clang-format \+ cpplint\).*Passed", "required": True},
]


def test_check_commit_passed_both():
    log = "Add Apache 2.0 license header....Passed\nCANN code style check (clang-format + cpplint)...Passed\n"
    res = check_commit_passed(log, CHECKS)
    assert res == {"license": True, "style": True}
    assert required_checks_passed(res, CHECKS) is True


def test_check_commit_passed_partial():
    log = "Add Apache 2.0 license header....Passed\nCANN code style check (clang-format + cpplint)...Failed\n"
    res = check_commit_passed(log, CHECKS)
    assert res["license"] is True and res["style"] is False
    assert required_checks_passed(res, CHECKS) is False


def test_custom_checks_decoupled_from_english():
    # 证明检查文案完全可配置：换成自定义 hook 名也能工作
    custom = [{"name": "my_hook", "pattern": r"My Custom Hook OK", "required": True}]
    assert check_commit_passed("... My Custom Hook OK ...", custom) == {"my_hook": True}


def test_build_branch_name():
    name = build_branch_name("feature/ai", "os.h")
    assert name.startswith("feature/ai-os-")


def test_build_commit_message():
    assert build_commit_message("add {filename}", "os.h") == "add os.h"


def test_dry_run_command_construction(tmp_path):
    cfg = Config.load(
        None, project_root=tmp_path,
        overrides={
            "paths": {"mylearn_repo": str(tmp_path / "repo")},
            "repo_verify": {"conda_sh": "", "clang_format_bin": "clang-format-14"},
        },
    )
    v = RepoVerifier(cfg, dry_run=True, verbose=False)
    v.git_add_and_commit("add os.h", "asc-stl/include/asc/std/__asc/os.h")
    v.run_clang_format(Path("/repo/x.h"))
    joined = "\n".join(v.commands)
    # shlex.quote 只在必要时加引号；纯安全字符路径保持原样
    assert "git add -- asc-stl/include/asc/std/__asc/os.h" in joined
    assert "git commit -s -m 'add os.h'" in joined
    assert "clang-format-14 -i /repo/x.h" in joined


def test_dry_run_commit_message_with_special_chars(tmp_path):
    # v2 把 message 直接拼进双引号字符串；这里用带引号/分号的 message 验证转义安全
    cfg = Config.load(None, project_root=tmp_path,
                      overrides={"repo_verify": {"conda_sh": ""}})
    v = RepoVerifier(cfg, dry_run=True, verbose=False)
    v.git_add_and_commit('weird "msg"; rm -rf /', "a/b.h")
    joined = "\n".join(v.commands)
    # 整个危险串应被作为单个被引号包裹的参数，不会拆出 rm 命令
    assert "rm -rf /'" in joined or "'weird" in joined
    assert "git commit -s -m " in joined
