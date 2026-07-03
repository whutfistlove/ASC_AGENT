"""knowledge_base 离线单测：加载真实 reference/、注入命中、白名单触发、缺库降级。

全部离线、确定性，不调模型、不需 CANN。
"""

from pathlib import Path

from core.common.config import Config
from core.knowledge.knowledge_base import KnowledgeBase, load_knowledge_base

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "reference"


def _kb() -> KnowledgeBase:
    return KnowledgeBase.load(REF)


def test_loads_real_reference_knowledge_base():
    kb = _kb()
    assert not kb.is_empty
    assert kb.layout == "manifest-v2"
    assert kb.mappings, "manifest 注册的 mappings 应被加载"
    assert any(s.get("always_inject") for s in kb.mappings)
    assert kb.segment_substitutions and kb.segment_substitutions[0]["from"] == "__cccl"
    assert kb.migration_policy.get("public_aggregation_headers")
    assert kb.grammar_rules, "grammar 规则集应被加载"
    assert kb.constraint_rules, "constraint 规则集应被加载"
    assert kb.rule_sets.get("implicit_dependency"), "泛化隐含依赖规则应被加载"
    assert kb.catalogs["runtime-api"]["path"].endswith("api-mapping/runtime_api.yaml")


def test_render_block_injects_universal_symbol_mappings():
    block = _kb().render_block("template <class _Tp> const _Tp& max(const _Tp&, const _Tp&);")
    # always_inject 的通用符号映射对每个头都应出现
    assert "_ASC_STD_BEGIN" in block
    assert "_ASC_AICORE_FN" in block
    assert "_LIBCUDACXX_BEGIN_NAMESPACE_STD" in block
    assert "_CUDA_VSTD::" in block
    assert "具体映射事实" in block


def test_grammar_rule_fires_on_device_qualifier():
    hit = _kb().relevant_for("__device__ int helper(int x) { return x; }")
    assert any("__device__" in str(r.get("cuda_form", "")) for r in hit["grammar"])


def test_constraint_fires_on_double_keyword():
    hit = _kb().relevant_for("__global__ void k(double* p) { p[0] = 1.0; }")
    assert any("double" in str(r.get("feature", "")).lower() for r in hit["constraints"])


def test_no_false_fire_on_common_tokens():
    # `#if defined`, `struct`, `value` 等常见词不应误触发约束/语法（白名单设计）
    src = "#if defined(__CCE__)\nstruct Foo { int value; };\ntemplate <class T> T id(T x){return x;}"
    hit = _kb().relevant_for(src)
    assert hit["grammar"] == []
    assert hit["constraints"] == []
    # 但 always_inject 的符号映射仍应在
    assert hit["symbols"]


def test_missing_reference_dir_degrades_to_empty(tmp_path):
    kb = KnowledgeBase.load(tmp_path / "does_not_exist")
    assert kb.is_empty
    assert kb.render_block("anything") == ""


def test_config_reference_dir_resolves_under_project_root():
    cfg = Config.load(settings_path=None, project_root=ROOT)
    assert cfg.reference_dir == REF


def test_load_knowledge_base_is_cached():
    a = load_knowledge_base(str(REF))
    b = load_knowledge_base(str(REF))
    assert a is b
