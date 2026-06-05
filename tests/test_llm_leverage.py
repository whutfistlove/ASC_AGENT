"""单测：让大模型能力被更充分发挥的几项改进（全部离线、用 MockModelClient 驱动）。

覆盖：
  * build_toolbox 工厂的门槛（tools_enabled / provider）。
  * distill_error_lines 日志蒸馏（抽 error 行 / 尾部回退 / 空输入）。
  * 生成期取证：初稿改写 与 测试迁移 都能在出结果前调用工具（RAG + 自检）。
  * MockModelClient.generate_with_tools 单次只记一条 calls、只消耗一条响应（无双计）。
  * 跨轮记忆：attempt_history 进入测试反馈修复请求。
  * 默认测试反馈把埋在噪音里的报错蒸馏出来（不再按字节硬截断截没）。
"""

import json
from pathlib import Path

import main
from core.agent_tools import AgentToolbox, build_toolbox, distill_error_lines
from core.config import Config
from core.fix_once import run_test_artifact_fix
from core.model_client import MockModelClient
from core.pipeline import Pipeline
from core.test_migrator import migrate_operator_tests


# --------------------------------------------------------------------------- #
# build_toolbox 工厂
# --------------------------------------------------------------------------- #
def _cfg(tmp_path, **model_over) -> Config:
    over = {
        "paths": {"output_dir": str(tmp_path / "outputs")},
        "repo_verify": {"conda_sh": ""},
    }
    if model_over:
        over["model"] = model_over
    return Config.load(None, project_root=main.PROJECT_ROOT, overrides=over)


def test_build_toolbox_gating(tmp_path):
    # 默认关闭 → None
    assert build_toolbox(_cfg(tmp_path)) is None
    # 开启但 provider=mock → None（离线 mock 不需要真实工具）
    assert build_toolbox(_cfg(tmp_path, provider="mock", tools_enabled=True)) is None
    # 开启且 provider=zhipu → 真实工具箱
    tb = build_toolbox(_cfg(tmp_path, provider="zhipu", tools_enabled=True))
    assert isinstance(tb, AgentToolbox)


# --------------------------------------------------------------------------- #
# 日志蒸馏
# --------------------------------------------------------------------------- #
def test_distill_extracts_error_drops_noise():
    text = "noise line\n" * 200 + "kernel.cpp:5:3: error: no matching function\n" + "tail\n" * 5
    out = distill_error_lines(text)
    assert "no matching function" in out
    assert out.count("\n") < 20  # 噪音被丢掉，只剩报错及上下文


def test_distill_tail_fallback_and_empty():
    out = distill_error_lines("alpha\nbeta\ngamma\n")
    assert "日志末尾" in out and "gamma" in out
    assert distill_error_lines("") == ""


# --------------------------------------------------------------------------- #
# 生成期取证：初稿改写能调用工具
# --------------------------------------------------------------------------- #
def _mini_project(tmp_path) -> tuple[Config, Path, AgentToolbox]:
    proj = tmp_path
    (proj / "skills").mkdir()
    (proj / "skills" / "rewrite_initial.md").write_text("p", encoding="utf-8")
    ex = proj / "examples" / "headers"
    ex.mkdir(parents=True)
    for n in ("max.cccl.h", "max.accl.h", "os.cccl.h", "os.accl.h"):
        (ex / n).write_text(f"// {n}\n", encoding="utf-8")
    accl = proj / "accl"
    inc = accl / "libascendcxx" / "include" / "ascend" / "std"
    inc.mkdir(parents=True)
    (inc / "__config").write_text("#define _ASCEND_AICORE_FN inline\n", encoding="utf-8")
    cfg = Config.load(
        None,
        project_root=proj,
        overrides={
            "paths": {"accl_repo": str(accl), "output_dir": str(proj / "outputs")},
            "model": {"provider": "mock"},
            "repo_verify": {"conda_sh": ""},
        },
    )
    toolbox = AgentToolbox(accl, proj / "outputs", host_include_dirs=[accl / "libascendcxx" / "include"])
    return cfg, accl, toolbox


def test_initial_rewrite_invokes_tools(tmp_path):
    cfg, _accl, toolbox = _mini_project(tmp_path)
    inp = tmp_path / "libcudacxx" / "include" / "cuda" / "std" / "__cccl" / "os.h"
    inp.parent.mkdir(parents=True)
    inp.write_text("#ifndef X\n#define X\n#endif // X\n", encoding="utf-8")

    initial = json.dumps(
        {"file_type": "os_h", "rewritten_code": "#ifndef G\n#define G\n#endif // G\n", "notes": "n"}
    )
    model = MockModelClient(
        responses=[initial],
        tool_script=[{"name": "read_repo_file",
                      "arguments": {"relpath": "libascendcxx/include/ascend/std/__config"}}],
    )
    pipeline = Pipeline(cfg, model, verifier=None, verbose=False, toolbox=toolbox)
    res = pipeline.convert_only(inp, write_to_repo=False)

    assert res.converted is True
    # 工具在出初稿前被调用（生成期取证）。
    assert toolbox.call_log and toolbox.call_log[0]["name"] == "read_repo_file"
    # 单次逻辑调用：只记一条 calls、且标记为带工具。
    assert len(model.calls) == 1 and model.calls[0].get("tools") is True


def test_initial_rewrite_without_toolbox_is_single_shot(tmp_path):
    cfg, _accl, _tb = _mini_project(tmp_path)
    inp = tmp_path / "libcudacxx" / "include" / "cuda" / "std" / "__cccl" / "os.h"
    inp.parent.mkdir(parents=True)
    inp.write_text("#ifndef X\n#define X\n#endif // X\n", encoding="utf-8")

    initial = json.dumps(
        {"file_type": "os_h", "rewritten_code": "#ifndef G\n#define G\n#endif // G\n", "notes": "n"}
    )
    model = MockModelClient(responses=[initial])
    pipeline = Pipeline(cfg, model, verifier=None, verbose=False, toolbox=None)
    res = pipeline.convert_only(inp, write_to_repo=False)

    assert res.converted is True
    # 未注入工具：保持旧的「单轮 prompt→JSON」，calls 不带 tools 标记。
    assert len(model.calls) == 1 and "tools" not in model.calls[0]


# --------------------------------------------------------------------------- #
# 生成期取证：测试迁移能调用工具
# --------------------------------------------------------------------------- #
def test_test_migration_invokes_tools(tmp_path):
    cfg = _cfg(tmp_path)
    accl = tmp_path / "accl"
    inc = accl / "libascendcxx" / "include" / "ascend" / "std"
    inc.mkdir(parents=True)
    (inc / "__config").write_text("#define _ASCEND_AICORE_FN inline\n", encoding="utf-8")
    toolbox = AgentToolbox(accl, tmp_path / "outputs", host_include_dirs=[accl / "libascendcxx" / "include"])

    payload = {
        "host_test_code": "static int g_failures=0;\nint main(){return g_failures==0?0:1;}",
        "kernel_spec": {"gm_inputs": 2, "input_init": "h_in0[i]=i;",
                        "element_op_code": "out0_val=in0_val;", "golden_code": "expected0=in0_ref;"},
        "notes": "n",
    }
    model = MockModelClient(
        responses=[json.dumps(payload)],
        tool_script=[{"name": "grep_repo", "arguments": {"pattern": "_ASCEND_AICORE_FN"}}],
    )
    arts = migrate_operator_tests(
        cfg, model,
        algo_name="max", include_path="ascend/std/__algorithm/max.h",
        target_relpath="libascendcxx/include/ascend/std/__algorithm/max.h",
        cccl_header_text="// c", accl_header_text="// a", cccl_test_text="// t",
        verbose=False, toolbox=toolbox,
    )
    assert arts.has_host() and arts.has_kernel()
    assert toolbox.call_log and toolbox.call_log[0]["name"] == "grep_repo"
    assert len(model.calls) == 1 and model.calls[0].get("tools") is True


# --------------------------------------------------------------------------- #
# 跨轮记忆
# --------------------------------------------------------------------------- #
def test_attempt_history_enters_fix_request(tmp_path):
    (tmp_path / "skills" / "_shared").mkdir(parents=True)
    (tmp_path / "skills" / "fix_tests_from_log.md").write_text("FIX", encoding="utf-8")
    cfg = Config.load(
        None, project_root=tmp_path,
        overrides={"paths": {"output_dir": str(tmp_path / "outputs")}, "repo_verify": {"conda_sh": ""}},
    )
    model = MockModelClient(
        responses=[json.dumps({"root_cause": "operator", "rewritten_code": "// x\n", "notes": "n"})]
    )
    run_test_artifact_fix(
        config=cfg, model_client=model,
        target_relpath="libascendcxx/include/ascend/std/__algorithm/max.h",
        expected_header_guard="G", header_text="// h", host_test_text="// host",
        kernel_spec=None, test_feedback_text="host_result: FAILED", round_index=1,
        attempt_history="- 第1轮：根因=operator；改动=[header]；结果=仍失败",
        verbose=False, toolbox=None,
    )
    req = (cfg.output_dir / "fix_request_test_round1.md").read_text(encoding="utf-8")
    assert "历次修复尝试与结果" in req and "第1轮" in req


def test_format_attempt_history_shape():
    rounds = [
        {"round": 1, "root_cause": "operator", "applied": ["header"], "passed": False},
        {"round": 2, "root_cause": "host_test", "applied": [], "passed": False, "test_error": "boom"},
    ]
    s = main._format_attempt_history(rounds)
    assert "第1轮" in s and "header" in s
    assert "第2轮" in s and "无改动" in s and "boom" in s
    assert main._format_attempt_history([]) == ""


# --------------------------------------------------------------------------- #
# 默认反馈蒸馏
# --------------------------------------------------------------------------- #
def test_feedback_distills_buried_error(tmp_path):
    log = tmp_path / "kernel_test_x.log"
    log.write_text(
        "noise\n" * 3000 + "Mismatch at index 3: got 5 expected 7\n" + "noise\n" * 20,
        encoding="utf-8",
    )
    tr = {"host_passed": True, "kernel_passed": False, "kernel_log_path": str(log)}
    fb = main._build_test_feedback_text(tr)
    assert "Mismatch at index 3" in fb       # 埋在 3000 行噪音后仍被抽出
    assert "已蒸馏" in fb
    assert len(fb) < 5000                     # 远小于原始日志
