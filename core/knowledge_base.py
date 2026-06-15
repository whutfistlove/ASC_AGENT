"""可审计知识库加载与检索（reference/）。

把照搬自官方 cuda2ascend-simt 的结构化知识库接进迁移管线：改写/测试迁移前，按当前
头文件涉及的符号，从 reference/ 里检索**命中的**符号映射 / 语法规则 / 约束规则，拼成一段
注入到模型提示词里——让模型「先查可审计知识库」，而不是凭记忆重推 CCCL→ASC 的映射。

设计与 core/example_retrieval.py 对齐：纯词法、离线、确定性，无外部依赖。
来源优先级：

* ``reference/symbol_mapping.yaml`` —— 本项目所在的「头文件层」符号/宏/命名空间映射，
  always_inject 的记录对每个头都注入（命名空间/修饰符这类通用规则）。
* ``reference/grammar_rules.yaml`` —— 官方语法改写规则（__device__/__shared__/assert/...），
  仅当其触发词出现在源码里才注入。
* ``reference/constraint_rules.yaml`` —— 官方不支持/受限特性，仅当高信号关键词
  （double/complex/texture/...）整词出现在源码里才注入。

官方 api-mapping/（runtime/device 层、945+230 条）与本层不同级，体量大，**不在此自动注入**；
需要时由专门查询函数按需检索，避免污染提示词。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

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


def _safe_yaml(path: Path) -> Any:
    """读 YAML；文件缺失/解析失败一律返回 None（保证干净检出/无 reference 时不崩）。"""
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None


def _as_list(doc: Any) -> list[dict]:
    return [x for x in doc if isinstance(x, dict)] if isinstance(doc, list) else []


@dataclass
class KnowledgeBase:
    reference_dir: Path
    symbols: list[dict] = field(default_factory=list)
    segment_substitutions: list[dict] = field(default_factory=list)
    migration_policy: dict = field(default_factory=dict)
    grammar_rules: list[dict] = field(default_factory=list)
    constraint_rules: list[dict] = field(default_factory=list)

    # ----- 加载 ----- #
    @classmethod
    def load(cls, reference_dir: Path | str) -> "KnowledgeBase":
        ref = Path(reference_dir)
        sym_doc = _safe_yaml(ref / "symbol_mapping.yaml")
        sym_doc = sym_doc if isinstance(sym_doc, dict) else {}
        return cls(
            reference_dir=ref,
            symbols=_as_list(sym_doc.get("symbols")),
            segment_substitutions=_as_list(sym_doc.get("segment_substitutions")),
            migration_policy=dict(sym_doc.get("migration_policy") or {}),
            grammar_rules=_as_list(_safe_yaml(ref / "grammar_rules.yaml")),
            constraint_rules=_as_list(_safe_yaml(ref / "constraint_rules.yaml")),
        )

    @property
    def is_empty(self) -> bool:
        return not (self.symbols or self.grammar_rules or self.constraint_rules)

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
        """返回命中当前源码的 symbols / grammar / constraints。"""
        src_tokens = _tokens(source_text)
        src_tokens_low = {t.lower() for t in src_tokens}

        symbols: list[dict] = []
        for s in self.symbols:
            if s.get("always_inject"):
                symbols.append(s)
                continue
            cccl = str(s.get("cccl", ""))
            if cccl and (_tokens(cccl) & src_tokens):
                symbols.append(s)

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
        return {"symbols": symbols, "grammar": grammar, "constraints": constraints}

    # ----- 渲染为提示词块 ----- #
    def render_block(self, source_text: str) -> str:
        """渲染成注入提示词的 Markdown 块；无命中则返回空串（不注入）。"""
        hit = self.relevant_for(source_text)
        symbols, grammar, constraints = hit["symbols"], hit["grammar"], hit["constraints"]
        if not (symbols or grammar or constraints):
            return ""

        lines = ["【reference/ 可审计知识库（命中项，按此映射，勿凭记忆臆造）】"]

        if symbols:
            lines.append("# 符号 / 宏 / 命名空间映射（CCCL → ASC-STL）")
            for s in symbols:
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
