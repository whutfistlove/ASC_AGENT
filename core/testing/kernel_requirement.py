"""判断一个头文件需不需要 kernel（AscendC/cannsim 设备侧）测试。

源 CCCL 库里有大量头只含编译期构造（类型特征、概念、宏、前向声明、host-stdlib 转发），
没有可在设备侧运行的「算子」——对它们跑 kernel 仿真既无意义又慢。这里先用确定性启发式
把每个头分成三类；实际测试工作流再调用模型独立判断并执行保守共识：只有规则和模型都认为
host-only 才跳过 kernel，分歧、模型不可用或输出不合法统一要求 kernel。

判定（优先级自上而下）：
1. 模块 ∈ HOST_ONLY_MODULES → ``host_only``。模块规则优先于内容信号：少数 type_trait 含
   constexpr 辅助函数（会命中设备函数正则），但它们没有可仿真的设备算子，仍应 host-only。
2. 内容含设备可调用函数（设备修饰宏后跟 ``name(``）→ ``kernel_applicable``。
3. 无设备函数但有明确 trait/编译期标记 → ``host_only``。
4. 其余 → ``unknown`` → 调用方回退到现有行为（照常尝试 kernel/smoke）。

设计与 inventory/dep_graph 对齐：纯词法、离线、确定性、可单测。
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field

from core.analysis.inventory import _strip_comments_and_literals

# host-only 模块：编译期/host 层，按设计没有设备侧算子。可被 config.kernel_host_only_modules 覆盖。
HOST_ONLY_MODULES: frozenset[str] = frozenset(
    {"__type_traits", "__host_stdlib", "__fwd", "__concepts"}
)

# 设备可调用函数：CCCL 设备修饰宏（迁移后为 _ASC_AICORE_FN）后，在同一条语句里出现 `name(`。
# 用 [^;{}\n] 限制在声明行内，避免跨语句误命中。
_DEVICE_FN_RE = re.compile(
    r"(?:_CCCL_API|_CCCL_HOST_DEVICE|_LIBCUDACXX_HIDE_FROM_ABI|_ASC_AICORE_FN)\b"
    r"[^;{}\n]*\b[A-Za-z_]\w*\s*\("
)

# 编译期/trait 标记：命中其一即认为是 trait/概念/纯宏头（无运行期算子）。
_TRAIT_MARKER_RE = re.compile(
    r"\bintegral_constant\b"
    r"|\bstatic\s+constexpr\b[^;\n]*\bvalue\b"
    r"|\binline\s+constexpr\s+bool\b"
    r"|\b_CCCL_CONCEPT\b"
    r"|\b_LIBCUDACXX_CONCEPT\b"
)

# CTAD（类模板实参推导）支持头：只产出推导指引，是纯编译期机制，无设备算子。
# 例如 __utility/ctad_support.h 的 _CCCL_CTAD_SUPPORTED_FOR_TYPE / __allow_ctad。
_CTAD_RE = re.compile(r"__allow_ctad|_CTAD_SUPPORTED_FOR_TYPE")


def _is_macro_only(code: str) -> bool:
    """剥离注释后的代码是否只剩预处理指令（纯宏头，无运行期算子）。

    先折叠 ``\\`` 续行（宏体续行不以 ``#`` 开头），再看是否每个非空逻辑行都是 ``#`` 指令。
    """
    joined = re.sub(r"\\\s*\n", " ", code)
    saw_directive = False
    for line in joined.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            saw_directive = True
        else:
            return False
    # 仅当确有预处理指令且无其它代码才算纯宏头；空/缺失内容不算（应回退 unknown 保守跑 kernel）。
    return saw_directive

HOST_ONLY = "host_only"
KERNEL_APPLICABLE = "kernel_applicable"
UNKNOWN = "unknown"


@dataclass(frozen=True)
class KernelRequirementDecision:
    """Auditable rule/model consensus for one header."""

    relpath: str
    rule_classification: str
    rule_needs_kernel_test: bool
    model_status: str
    model_classification: str = ""
    model_needs_kernel_test: bool | None = None
    model_reason: str = ""
    model_evidence: list[str] = field(default_factory=list)
    agreement: bool = False
    needs_kernel_test: bool = True
    resolution: str = "conservative_kernel"
    source_sha256: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def module_of(relpath: str) -> str:
    """从头相对路径取「模块」：首个 ``__`` 段；没有则取父目录名（再退到文件名 stem）。

    兼容 CCCL 源键（``__type_traits/foo.h``）、整树键（``std/__type_traits/foo.h``）、
    以及 ACCL 目标 relpath（``asc-stl/include/asc/std/__type_traits/foo.h``）。
    """
    parts = [p for p in str(relpath).replace("\\", "/").split("/") if p]
    for part in parts:
        if part.startswith("__"):
            return part
    if len(parts) >= 2:
        return parts[-2]
    return parts[-1].rsplit(".", 1)[0] if parts else ""


def classify_kernel_requirement(
    relpath: str,
    source_text: str,
    *,
    host_only_modules: frozenset[str] | set[str] | None = None,
) -> str:
    """返回 ``host_only`` / ``kernel_applicable`` / ``unknown``（见模块 docstring）。"""
    modules = host_only_modules if host_only_modules is not None else HOST_ONLY_MODULES
    if module_of(relpath) in modules:
        return HOST_ONLY

    code = _strip_comments_and_literals(source_text or "")
    # 设备函数优先：即便同时含 CTAD 指引（如 __functional/operations.h 既有 plus/minus
    # 设备算子又有 _CCCL_CTAD_SUPPORTED_FOR_TYPE），有真实设备算子就需要 kernel。
    if _DEVICE_FN_RE.search(code):
        return KERNEL_APPLICABLE
    # 纯编译期：CTAD 推导指引 / 纯宏头 / trait·概念 —— 无设备算子，host-only。
    if _CTAD_RE.search(code):
        return HOST_ONLY
    if _is_macro_only(code):
        return HOST_ONLY
    if _TRAIT_MARKER_RE.search(code):
        return HOST_ONLY
    return UNKNOWN


def needs_kernel_test(
    relpath: str,
    source_text: str,
    *,
    host_only_modules: frozenset[str] | set[str] | None = None,
) -> bool:
    """host_only 返回 False（跳过 kernel）；kernel_applicable / unknown 返回 True（保守跑）。"""
    return classify_kernel_requirement(
        relpath, source_text, host_only_modules=host_only_modules
    ) != HOST_ONLY


def _decision_tag(relpath: str) -> str:
    tag = re.sub(r"[^0-9A-Za-z_]+", "_", str(relpath)).strip("_")
    return tag[-120:] or "header"


def _model_request(relpath: str, source_text: str, target_text: str) -> str:
    return f"""【header_relpath】
{relpath}

【CCCL 源头文件】
{source_text}

【已迁移 ACCL 头（可能为空或未完成，仅作辅助证据）】
{target_text}
"""


def decide_kernel_requirement(
    *,
    config,
    model_client,
    relpath: str,
    source_text: str,
    target_text: str = "",
    host_only_modules: frozenset[str] | set[str] | None = None,
    show_model_io: bool = False,
) -> KernelRequirementDecision:
    """Combine deterministic and model judgments with a kernel-safe policy.

    Agreement preserves the shared answer. Any disagreement or model failure
    resolves to ``needs_kernel_test=True``. The function never raises for model
    errors, so a flaky judge cannot accidentally suppress device validation.
    """
    rule_classification = classify_kernel_requirement(
        relpath, source_text, host_only_modules=host_only_modules
    )
    rule_needs = rule_classification != HOST_ONLY
    source_sha256 = hashlib.sha256((source_text or "").encode("utf-8")).hexdigest()
    base = {
        "relpath": relpath,
        "rule_classification": rule_classification,
        "rule_needs_kernel_test": rule_needs,
        "source_sha256": source_sha256,
    }

    from core.common.utils import call_model_with_io, save_text

    output_dir = config.model_output_dir
    tag = _decision_tag(relpath)

    def _save_result(decision: KernelRequirementDecision) -> KernelRequirementDecision:
        save_text(
            output_dir / f"kernel_requirement_result_{tag}.json",
            json.dumps(decision.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        return decision

    if model_client is None:
        return _save_result(
            KernelRequirementDecision(
                **base,
                model_status="unavailable",
                needs_kernel_test=True,
                resolution="model_unavailable_requires_kernel",
            )
        )

    from core.llm.model_client import extract_json_object

    request = _model_request(relpath, source_text, target_text)
    save_text(output_dir / f"kernel_requirement_request_{tag}.md", request)
    raw = ""
    try:
        raw = call_model_with_io(
            model_client,
            stage=f"kernel 适用性判定（{relpath}）",
            system_prompt=config.read_skill("judge_kernel_requirement.md"),
            user_content=request,
            show_io=show_model_io,
        )
        save_text(output_dir / f"kernel_requirement_raw_{tag}.md", raw)
        data = extract_json_object(raw, strict=True)
        model_value = data.get("needs_kernel_test")
        classification = str(data.get("classification") or "")
        if type(model_value) is not bool:  # bool only; reject 0/1 and truthy strings
            raise ValueError("needs_kernel_test 必须是 JSON boolean")
        if classification not in {HOST_ONLY, KERNEL_APPLICABLE}:
            raise ValueError("classification 必须是 host_only 或 kernel_applicable")
        if (classification == KERNEL_APPLICABLE) != model_value:
            raise ValueError("classification 与 needs_kernel_test 相互矛盾")
        evidence_raw = data.get("evidence") or []
        evidence = [str(item) for item in evidence_raw] if isinstance(evidence_raw, list) else []
        agreement = model_value == rule_needs
        final = rule_needs if agreement else True
        decision = KernelRequirementDecision(
            **base,
            model_status="ok",
            model_classification=classification,
            model_needs_kernel_test=model_value,
            model_reason=str(data.get("reason") or "").strip(),
            model_evidence=evidence,
            agreement=agreement,
            needs_kernel_test=final,
            resolution="agreement" if agreement else "disagreement_requires_kernel",
        )
    except Exception as exc:
        decision = KernelRequirementDecision(
            **base,
            model_status="error",
            model_reason=f"{type(exc).__name__}: {exc}",
            needs_kernel_test=True,
            resolution="model_error_requires_kernel",
        )

    return _save_result(decision)
