"""P2 单测：skill 的 {{include: _shared/xxx.md}} 片段展开与防循环。"""

import pytest

from core.config import Config


def _cfg(tmp_path) -> Config:
    (tmp_path / "skills" / "_shared").mkdir(parents=True)
    return Config.load(None, project_root=tmp_path, overrides={"repo_verify": {"conda_sh": ""}})


def test_include_is_expanded(tmp_path):
    cfg = _cfg(tmp_path)
    (tmp_path / "skills" / "_shared" / "frag.md").write_text("SHARED-RULE", encoding="utf-8")
    (tmp_path / "skills" / "main.md").write_text(
        "head\n{{include: _shared/frag.md}}\ntail", encoding="utf-8"
    )
    out = cfg.read_skill("main.md")
    assert "SHARED-RULE" in out
    assert "{{include" not in out
    assert out == "head\nSHARED-RULE\ntail"


def test_nested_include(tmp_path):
    # include 指令需独占一行（锚定行首），片段内可再引用其它片段。
    cfg = _cfg(tmp_path)
    (tmp_path / "skills" / "_shared" / "a.md").write_text("A\n{{include: _shared/b.md}}", encoding="utf-8")
    (tmp_path / "skills" / "_shared" / "b.md").write_text("B", encoding="utf-8")
    (tmp_path / "skills" / "main.md").write_text("{{include: _shared/a.md}}", encoding="utf-8")
    assert cfg.read_skill("main.md") == "A\nB"


def test_include_cycle_raises(tmp_path):
    cfg = _cfg(tmp_path)
    (tmp_path / "skills" / "x.md").write_text("{{include: y.md}}", encoding="utf-8")
    (tmp_path / "skills" / "y.md").write_text("{{include: x.md}}", encoding="utf-8")
    with pytest.raises(ValueError, match="循环"):
        cfg.read_skill("x.md")


def test_no_include_is_passthrough(tmp_path):
    cfg = _cfg(tmp_path)
    (tmp_path / "skills" / "plain.md").write_text("just text", encoding="utf-8")
    assert cfg.read_skill("plain.md") == "just text"
