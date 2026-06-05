"""core/build_env 单测：CANN 工具探测与 PATH 补齐（环境无关的可判定部分）。"""

from pathlib import Path

from core import build_env


def test_cann_bin_candidates_are_paths():
    cands = build_env.cann_bin_candidates()
    assert isinstance(cands, list) and all(isinstance(p, Path) for p in cands)
    # 至少包含标准 CANN 安装下的 bin 目录候选。
    assert any("Ascend" in str(p) for p in cands)


def test_tool_reachable_false_for_nonexistent():
    assert build_env.tool_reachable("definitely_not_a_real_tool_xyz_123") is False


def test_missing_kernel_tools_returns_list():
    out = build_env.missing_kernel_tools()
    assert out == [] or out == ["cannsim"]


def test_cann_path_additions_only_for_unreachable(monkeypatch):
    # 当工具都"可达"时，不应补任何 PATH 目录。
    monkeypatch.setattr(build_env.shutil, "which", lambda name: "/usr/bin/" + name)
    assert build_env.cann_path_additions() == []
