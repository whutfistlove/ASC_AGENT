"""单测：best-of-N 采样择优（纯逻辑 + 打分器 + pipeline 集成，全离线）。"""

import json
from pathlib import Path

import pytest

from core.common.config import Config
from core.llm.best_of_n import best_of_n, score_header_code, score_host_test_code
from core.llm.model_client import MockModelClient
from core.migration.pipeline import Pipeline


# --------------------------------------------------------------------------- #
# 纯逻辑
# --------------------------------------------------------------------------- #
def test_best_of_n_picks_highest_score():
    seq = iter(["a", "bb", "ccc"])
    res, raw, scores = best_of_n(lambda: next(seq), parse=lambda s: s, score=lambda s: float(len(s)), n=3)
    assert res == "ccc" and raw == "ccc"
    assert scores == [1.0, 2.0, 3.0]


def test_best_of_n_skips_parse_failures():
    seq = iter(["bad", "ok"])

    def parse(s):
        if s == "bad":
            raise ValueError("nope")
        return s

    res, raw, scores = best_of_n(lambda: next(seq), parse, lambda s: 1.0, n=2)
    assert res == "ok" and raw == "ok"
    assert scores[0] == float("-inf")


def test_best_of_n_all_fail_raises_last_parse_error():
    def parse(_s):
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        best_of_n(lambda: "x", parse, lambda s: 0.0, n=2)


def test_n_one_calls_generate_once():
    calls = {"n": 0}

    def gen():
        calls["n"] += 1
        return "x"

    best_of_n(gen, parse=lambda s: s, score=lambda s: 0.0, n=1)
    assert calls["n"] == 1


# --------------------------------------------------------------------------- #
# 打分器
# --------------------------------------------------------------------------- #
def test_score_header_prefers_correct_guard_and_balance():
    guard = "G_H_"
    good = "#ifndef G_H_\n#define G_H_\nnamespace asc::std {}\n#endif // G_H_\n"
    bad = "int x;\n"
    assert score_header_code(good, guard) > score_header_code(bad, guard)
    # 指令不配平要被罚分。
    unbalanced = "#ifndef G_H_\n#define G_H_\n// missing endif\n"
    assert score_header_code(unbalanced, guard) < score_header_code(good, guard)


def test_score_host_test_uses_toolbox_verdict():
    class _TB:
        def __init__(self, verdict):
            self.verdict = verdict

        def host_syntax_check(self, code):
            return self.verdict

    code = "#include <cassert>\nint main(){return 0;}"
    ok = score_host_test_code(code, _TB("OK：语法通过"))
    bad = score_host_test_code(code, _TB("FAILED：\nerror: ..."))
    assert ok > bad


# --------------------------------------------------------------------------- #
# pipeline 集成：draft_samples=2 时择优写出结构更优的初稿
# --------------------------------------------------------------------------- #
def test_pipeline_best_of_n_selects_better_header(tmp_path):
    proj = tmp_path
    (proj / "skills").mkdir()
    (proj / "skills" / "rewrite_initial.md").write_text("p", encoding="utf-8")
    ex = proj / "examples" / "headers"
    ex.mkdir(parents=True)
    for n in ("max.cccl.h", "max.accl.h", "os.cccl.h", "os.accl.h"):
        (ex / n).write_text(f"// {n}\n", encoding="utf-8")

    cfg = Config.load(
        None, project_root=proj,
        overrides={
            "paths": {"accl_repo": str(proj / "accl"), "output_dir": str(proj / "outputs")},
            "model": {"provider": "mock", "draft_samples": 2},
            "repo_verify": {"conda_sh": ""},
        },
    )
    inp = proj / "libcudacxx" / "include" / "cuda" / "std" / "__cccl" / "os.h"
    inp.parent.mkdir(parents=True)
    inp.write_text("#ifndef X\n#define X\n#endif // X\n", encoding="utf-8")

    weak = json.dumps({"file_type": "os_h", "rewritten_code": "broken no directives\n", "notes": "weak"})
    strong = json.dumps({
        "file_type": "os_h",
        "rewritten_code": "#ifndef G\n#define G\nnamespace asc::std {}\n#endif // G\n",
        "notes": "strong",
    })
    model = MockModelClient(responses=[weak, strong])  # 顺序：先弱后强，验证按分择优而非取第一个

    pipeline = Pipeline(cfg, model, verifier=None, verbose=False)
    res = pipeline.convert_only(inp, write_to_repo=False)

    assert res.converted is True
    assert len(model.calls) == 2  # 采样 2 次
    written = (cfg.model_output_dir / "rewritten_target.h").read_text(encoding="utf-8")
    assert "#ifndef G" in written and "broken no directives" not in written
