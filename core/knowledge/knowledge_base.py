"""可审计知识库加载与检索（reference/）。

把照搬自官方 cuda2ascend-simt 的结构化知识库接进迁移管线：改写/测试迁移前，按当前
头文件涉及的符号，从 reference/ 里检索**命中的**符号映射 / 语法规则 / 约束规则，拼成一段
注入到模型提示词里——让模型「先查可审计知识库」，而不是凭记忆重推 CCCL→ASC 的映射。

设计与 core/example_retrieval.py 对齐：纯词法、离线、确定性，无外部依赖。
``reference/manifest.yaml`` 把知识分成两类：

* ``mappings/``：宏、命名空间、include、路径、API 等具体映射事实；
* ``rules/``：语法、约束、隐含依赖等可复用匹配规则。

官方 api-mapping/（runtime/device 层、945+230 条）与本层不同级，体量大，**不在此自动注入**；
需要时由专门查询函数按需检索，避免污染提示词。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from core.knowledge.reference_loader import load_reference_bundle

_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

# 高信号触发词白名单：只有这些 CUDA 特性关键词整词出现在源码里时，才注入对应规则。
# 白名单（而非黑名单）能避免 `#if defined(...)`、`struct`、`value` 这类常见词误触发。
_TRIGGER_VOCAB = {
    "double", "complex", "texture", "nvrtc", "cooperative", "occupancy",
    "mmap", "opengl", "atomic", "warp", "shared", "printf", "assert",
}


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall(text or "")}


def _tokens_lower(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text or "")}


@dataclass
class KnowledgeBase:
    reference_dir: Path
    mappings: list[dict] = field(default_factory=list)
    rule_sets: dict[str, list[dict]] = field(default_factory=dict)
    segment_substitutions: list[dict] = field(default_factory=list)
    migration_policy: dict = field(default_factory=dict)
    catalogs: dict[str, dict] = field(default_factory=dict)
    layout: str = "empty"

    # ----- 加载 ----- #
    @classmethod
    def load(cls, reference_dir: Path | str) -> "KnowledgeBase":
        ref = Path(reference_dir)
        bundle = load_reference_bundle(ref, strict=False)
        return cls(
            reference_dir=ref,
            mappings=bundle.mappings,
            rule_sets=bundle.rules,
            segment_substitutions=bundle.segment_substitutions,
            migration_policy=bundle.migration_policy,
            catalogs=bundle.catalogs,
            layout=bundle.layout,
        )

    @property
    def symbols(self) -> list[dict]:
        """Compatibility alias for callers written against the v1 layout."""
        return self.mappings

    @property
    def grammar_rules(self) -> list[dict]:
        return list(self.rule_sets.get("grammar", []))

    @property
    def constraint_rules(self) -> list[dict]:
        return list(self.rule_sets.get("constraint", []))

    @property
    def is_empty(self) -> bool:
        return not (self.mappings or self.rule_sets)

    # ----- 检索 ----- #
    def _grammar_triggers(self, rule: dict) -> set[str]:
        """从语法规则推出触发词：cuda_form 里的 __xxx__ 修饰符 + 白名单命中的 pattern/词。"""
        triggers: set[str] = set()
        cuda_form = str(rule.get("cuda_form", "")) + " " + str(rule.get("pattern", ""))
        for tok in _TOKEN_RE.findall(cuda_form):
            low = tok.lower()
            if tok.startswith("__") and tok.endswith("__"):
                triggers.add(tok)            # __device__ / __shared__ / __global__
            elif low in _TRIGGER_VOCAB:
                triggers.add(low)            # assert / printf / shared / atomic ...
        return triggers

    def _constraint_triggers(self, rule: dict) -> set[str]:
        """约束规则触发词：feature 里命中白名单的关键词（整词匹配）。"""
        feat = str(rule.get("feature", ""))
        return {t.lower() for t in _TOKEN_RE.findall(feat) if t.lower() in _TRIGGER_VOCAB}

    def relevant_for(self, source_text: str, *, max_rules: int = 8) -> dict[str, list[dict]]:
        """返回命中当前源码的 mappings / grammar / constraints。"""
        src_tokens = _tokens(source_text)
        src_tokens_low = {t.lower() for t in src_tokens}

        mappings: list[dict] = []
        for s in self.mappings:
            if s.get("always_inject"):
                mappings.append(s)
                continue
            cccl = str(s.get("cccl", ""))
            if cccl and (_tokens(cccl) & src_tokens):
                mappings.append(s)

        def _fire(triggers: set[str]) -> bool:
            for trig in triggers:
                if trig.startswith("__") and trig.endswith("__"):
                    if trig in source_text:        # 含特殊字符，子串匹配
                        return True
                elif trig in src_tokens_low:        # 普通关键词，整词匹配
                    return True
            return False

        grammar = [r for r in self.grammar_rules if _fire(self._grammar_triggers(r))][:max_rules]
        constraints = [r for r in self.constraint_rules if _fire(self._constraint_triggers(r))][:max_rules]
        return {
            "mappings": mappings,
            "symbols": mappings,  # v1 compatibility
            "grammar": grammar,
            "constraints": constraints,
        }

    # ----- 渲染为提示词块 ----- #
    def render_block(self, source_text: str) -> str:
        """渲染成注入提示词的 Markdown 块；无命中则返回空串（不注入）。"""
        hit = self.relevant_for(source_text)
        mappings, grammar, constraints = hit["mappings"], hit["grammar"], hit["constraints"]
        if not (mappings or grammar or constraints):
            return ""

        lines = ["【reference/ 可审计知识库（命中项，按此映射，勿凭记忆臆造）】"]

        if mappings:
            lines.append("# 具体映射事实（宏 / 命名空间 / include，CCCL → ASC-STL）")
            for s in mappings:
                note = str(s.get("note", "")).strip()
                suffix = f"  // {note}" if note else ""
                lines.append(f"- `{s.get('cccl', '')}` → `{s.get('asc', '')}`{suffix}")

        if grammar:
            lines.append("# 适用语法改写规则")
            for r in grammar:
                lines.append(
                    f"- `{r.get('cuda_form', r.get('pattern', ''))}` → "
                    f"`{r.get('ascend_form', '')}`（{r.get('action', '')}）"
                )

        if constraints:
            lines.append("# 适用约束（不支持/受限，命中即按 action 处理）")
            for r in constraints:
                lines.append(
                    f"- {r.get('feature', '')}：{r.get('status', '')} / {r.get('action', '')}"
                    + (f" —— {r.get('workaround')}" if r.get("workaround") else "")
                )

        return "\n".join(lines)


@lru_cache(maxsize=8)
def load_knowledge_base(reference_dir: str) -> KnowledgeBase:
    """带缓存的加载（按 reference_dir 路径缓存，单次 CLI 运行内复用）。"""
    return KnowledgeBase.load(reference_dir)
