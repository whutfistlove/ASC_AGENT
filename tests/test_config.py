"""config 单测：env 展开、深合并、conda 探测、校验、安全 shell 构造。"""

from pathlib import Path

import pytest

from core import config as cfgmod
from core.config import Config, _deep_merge, _expand_str, detect_conda_sh


def test_expand_simple(monkeypatch):
    monkeypatch.setenv("FOO", "bar")
    assert _expand_str("${FOO}/x", {}) == "bar/x"


def test_expand_default_used_when_missing(monkeypatch):
    monkeypatch.delenv("NOPE", raising=False)
    assert _expand_str("${NOPE:-fallback}", {}) == "fallback"


def test_expand_nested_default(monkeypatch):
    monkeypatch.delenv("MYLEARN_REPO", raising=False)
    out = _expand_str("${MYLEARN_REPO:-${HOME}/projects/mylearn}", {"HOME": "/home/u"})
    assert out == "/home/u/projects/mylearn"


def test_expand_injected_wins_over_env(monkeypatch):
    monkeypatch.setenv("HOME", "/env/home")
    assert _expand_str("${HOME}", {"HOME": "/injected"}) == "/injected"


def test_expand_unresolved_kept_literal(monkeypatch):
    monkeypatch.delenv("UNSET_X", raising=False)
    assert _expand_str("${UNSET_X}", {}) == "${UNSET_X}"


def test_deep_merge_overrides_scalar_and_keeps_others():
    base = {"a": 1, "b": {"c": 2, "d": 3}}
    over = {"b": {"c": 99}}
    merged = _deep_merge(base, over)
    assert merged == {"a": 1, "b": {"c": 99, "d": 3}}


def test_deep_merge_list_replaced():
    base = {"checks": [{"name": "x"}]}
    over = {"checks": [{"name": "y"}]}
    assert _deep_merge(base, over)["checks"] == [{"name": "y"}]


def test_detect_conda_sh_from_conda_exe(monkeypatch, tmp_path):
    conda_sh = tmp_path / "miniconda3" / "etc" / "profile.d" / "conda.sh"
    conda_sh.parent.mkdir(parents=True)
    conda_sh.write_text("")
    monkeypatch.setenv("CONDA_EXE", str(tmp_path / "miniconda3" / "bin" / "conda"))
    monkeypatch.delenv("CONDA_PREFIX", raising=False)
    assert detect_conda_sh() == str(conda_sh)


def test_load_minimal_settings_applies_defaults(tmp_path):
    settings = tmp_path / "settings.yaml"
    settings.write_text("project:\n  name: custom\n", encoding="utf-8")
    cfg = Config.load(settings, project_root=tmp_path)
    assert cfg.raw["project"]["name"] == "custom"
    # 未覆盖项回退默认
    assert cfg.source_repo_prefix == "libcudacxx/include/cuda/std"
    assert cfg.max_fix_rounds == 5


def test_load_overrides(tmp_path):
    cfg = Config.load(None, project_root=tmp_path, overrides={"model": {"provider": "mock"}})
    assert cfg.model_provider == "mock"


def test_project_root_expanded_in_examples(tmp_path):
    cfg = Config.load(None, project_root=tmp_path)
    e1 = cfg.example_paths()["example_1"]["cccl"]
    assert e1 == str((tmp_path / "examples" / "example1_cccl.h"))


def test_validate_rejects_zero_rounds(tmp_path):
    with pytest.raises(ValueError):
        Config.load(None, project_root=tmp_path, overrides={"retry": {"max_fix_rounds": 0}})


def test_validate_rejects_empty_checks(tmp_path):
    with pytest.raises(ValueError):
        Config.load(None, project_root=tmp_path, overrides={"repo_verify": {"checks": []}})


def test_build_shell_script_quotes_and_activates(tmp_path):
    cfg = Config.load(
        None, project_root=tmp_path,
        overrides={
            "paths": {"mylearn_repo": "/repo with space"},
            "repo_verify": {"conda_sh": "/c/conda.sh", "conda_env": "myenv"},
        },
    )
    script = cfg.build_shell_script("git status")
    assert "source /c/conda.sh" in script
    assert "conda activate myenv" in script
    # 含空格路径必须被正确转义
    assert "cd '/repo with space'" in script
    assert script.strip().startswith("set -e")


def test_build_shell_script_without_conda(tmp_path):
    cfg = Config.load(
        None, project_root=tmp_path,
        overrides={"repo_verify": {"conda_sh": ""}},
    )
    # 自动探测在本测试环境通常找不到 -> 空 -> 不应出现 conda activate
    script = cfg.build_shell_script("echo hi", cd_repo=False)
    assert "conda activate" not in script or cfg.repo_verify["conda_sh"]
