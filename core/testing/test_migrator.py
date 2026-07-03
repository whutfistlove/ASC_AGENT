"""算子测试迁移：让大模型把 CCCL 侧测试翻译成 ACCL 侧测试。

与 core/fix_once.py 同风格：通过注入的 model_client 调模型，便于 mock 下测试。

产出（MigratedTests）：
    * host_test_code —— 完整的 asc/host/<algo>_tests.cpp，逐条打印用例数值；
    * kernel_spec    —— kernel 仿真测试的“算子相关槽位”（input_init / element_op_code /
      golden_code / gm_inputs）。其余 AscendC 设备流水线与 ACL/cannsim 由固定脚手架提供。

设计要点：
    * golden_code 必须是**独立**参考实现，绝不调用 asc::std::<algo>，从而消除
      “期望值与被测函数同源”的自洽假绿。
    * 算子语义以 CCCL/ACCL 头为基准；测试适配算子真实形态（二元返回值 / 原地 void /
      三参等），不得为凑模板而篡改算子签名。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from core.analysis.migration_state import VALIDATED_STATUSES
from core.analysis.test_index import CCCLTestIndexEntry, CCCLTestIndexReport
from core.common.config import Config
from core.common.utils import call_model_maybe_tools, call_model_with_io, read_text_file, save_text
from core.knowledge.example_retrieval import select_test_examples
from core.knowledge.knowledge_base import load_knowledge_base
from core.llm.best_of_n import best_of_n, score_host_test_code
from core.llm.model_client import BaseModelClient, extract_json_object
from core.testing.operator_kernel_scaffold import KernelScaffoldBuilder

# kernel_spec 必填槽位。gm_inputs/gm_outputs 控制脚手架生成多少个 GM 输入/输出；
# 旧 spec 未提供 gm_outputs 时等价于单输出。
_KERNEL_SPEC_REQUIRED = ("input_init", "element_op_code", "golden_code")
_MAX_GM_INPUTS = 8
_MAX_GM_OUTPUTS = 8
DEFAULT_TEST_PLAN_REPORT_NAME = "test_migration_plan.json"

_HOST_NONZERO_LITERAL_RETURN_RE = re.compile(r"\breturn\s+(?:[1-9]\d*|EXIT_FAILURE)\s*;")
_HOST_FAILURE_STATUS_RETURN_RE = re.compile(
    r"\breturn\s+[^;]*(?:fail|error|status)[^;]*;",
    flags=re.IGNORECASE,
)
_HOST_SUCCESS_TERNARY_RETURN_RE = re.compile(
    r"\breturn\s+[^;]*(?:ok|passed)[^;]*\?\s*0\s*:\s*(?:[1-9]\d*|EXIT_FAILURE)\s*;",
    flags=re.IGNORECASE,
)
_HOST_EXPECTED_USES_TESTED_API_RE = re.compile(
    r"\b(?:[\w:<>]+\s+)*(?:expected|golden|oracle|reference)\w*\s*=\s*[^;]*\basc::std::",
    flags=re.IGNORECASE,
)
# 依赖「已就绪、可选其测试」的状态集合，复用 migration_state 的单一事实源。
_SAFE_DEPENDENCY_STATUSES = VALIDATED_STATUSES
_TEST_DIRECTORY_PREFIX_BY_MODULE = {
    "__algorithm": "algorithms/",
    "__functional": "utilities/",
    "__numeric": "numerics/",
    "__type_traits": "utilities/",
    "__utility": "utilities/",
}


@dataclass(frozen=True)
class UpstreamTestDecision:
    relative_path: str
    kind: str
    decision: str
    reason: str
    candidate_headers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "candidate_headers": list(self.candidate_headers),
            "decision": self.decision,
            "kind": self.kind,
            "reason": self.reason,
            "relative_path": self.relative_path,
        }


@dataclass(frozen=True)
class UpstreamTestPlan:
    entry_header: str
    selected_tests: list[UpstreamTestDecision]
    deferred_tests: list[UpstreamTestDecision]
    selected_test_text: str = ""

    def summary(self) -> dict:
        by_reason: dict[str, int] = {}
        by_kind: dict[str, int] = {}
        for item in self.deferred_tests:
            by_reason[item.reason] = by_reason.get(item.reason, 0) + 1
            by_kind[item.kind] = by_kind.get(item.kind, 0) + 1
        return {
            "deferred_count": len(self.deferred_tests),
            "deferred_kind_counts": dict(sorted(by_kind.items())),
            "deferred_reason_counts": dict(sorted(by_reason.items())),
            "selected_count": len(self.selected_tests),
        }

    def to_dict(self, *, include_selected_test_text: bool = False) -> dict:
        payload = {
            "deferred_tests": [d.to_dict() for d in self.deferred_tests],
            "entry_header": self.entry_header,
            "summary": self.summary(),
            "selected_test_count": len(self.selected_tests),
            "selected_tests": [d.to_dict() for d in self.selected_tests],
        }
        if include_selected_test_text:
            payload["selected_test_text"] = self.selected_test_text
        return payload


@dataclass
class MigratedTests:
    algo_name: str
    host_test_code: str = ""
    kernel_spec: dict = field(default_factory=dict)
    notes: str = ""
    upstream_test_plan: UpstreamTestPlan | None = None

    def has_host(self) -> bool:
        return bool(self.host_test_code.strip())

    def has_kernel(self) -> bool:
        return bool(self.kernel_spec) and all(
            str(self.kernel_spec.get(k, "")).strip() for k in _KERNEL_SPEC_REQUIRED
        )


def _normalize_count(value, *, default: int, minimum: int, maximum: int) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError):
        return default
    if count < minimum or count > maximum:
        return default
    return count


def validate_kernel_spec(spec: dict) -> dict:
    """校验/规整 kernel_spec：确保必填槽位存在且为字符串，IO 数量在脚手架范围内。"""
    if not isinstance(spec, dict):
        raise ValueError(f"kernel_spec 必须是对象，实际为: {type(spec).__name__}")
    missing = [k for k in _KERNEL_SPEC_REQUIRED if not str(spec.get(k, "")).strip()]
    if missing:
        raise ValueError(f"kernel_spec 缺少必填槽位: {missing}")
    if "asc::std::" in str(spec.get("golden_code", "")):
        raise ValueError("kernel_spec.golden_code 必须使用独立 golden logic，禁止调用 asc::std::*")
    out = {k: str(spec[k]) for k in _KERNEL_SPEC_REQUIRED}
    out["gm_inputs"] = _normalize_count(
        spec.get("gm_inputs", 2), default=2, minimum=1, maximum=_MAX_GM_INPUTS
    )
    out["gm_outputs"] = _normalize_count(
        spec.get("gm_outputs", 1), default=1, minimum=1, maximum=_MAX_GM_OUTPUTS
    )
    # Node 13: kernel_spec 落盘时总是写明 dtype / inputs / outputs，便于审计。
    out["dtype"] = KernelScaffoldBuilder.dtype(spec)
    return out


def validate_host_test_code(code: object, *, algo_name: str = "") -> str:
    """校验模型生成的 host 测试。

    host 测试是语义验收的主入口，不能只打印 FAIL 后仍然 return 0。这里做轻量
    静态校验：测试可以用 assert 直接中止，也可以显式 return 1/EXIT_FAILURE，
    或基于 failures/ok/status 等状态表达式返回非零。
    """
    if not isinstance(code, str) or not code.strip():
        raise ValueError("模型输出缺少 host_test_code")
    text = code.strip()
    if _HOST_EXPECTED_USES_TESTED_API_RE.search(text):
        name = f" {algo_name}" if algo_name else ""
        raise ValueError(f"host_test_code{name} 的 expected/golden 必须使用独立逻辑，禁止调用 asc::std::*")
    if (
        re.search(r"\bassert\s*\(", text)
        or _HOST_NONZERO_LITERAL_RETURN_RE.search(text)
        or _HOST_FAILURE_STATUS_RETURN_RE.search(text)
        or _HOST_SUCCESS_TERNARY_RETURN_RE.search(text)
    ):
        return text + "\n" if not text.endswith("\n") else text
    raise ValueError("host_test_code 必须在任一用例失败时返回非零，不能只打印 FAIL 后 return 0")


def _index_entries_by_path(test_index: CCCLTestIndexReport) -> dict[str, CCCLTestIndexEntry]:
    return {entry.relative_path: entry for entry in test_index.tests}


def _mapped_test_paths(test_index: CCCLTestIndexReport, entry_header: str) -> list[str]:
    for mapping in test_index.mappings:
        if mapping.header == entry_header:
            return list(mapping.tests)
    return []


def _test_stem(relative_path: str) -> str:
    stem = Path(relative_path).name
    for suffix in (".pass.cpp", ".verify.cpp", ".fail.cpp"):
        if stem.endswith(suffix):
            return stem[: -len(suffix)]
    return Path(stem).stem


def _entry_module(entry_header: str) -> str:
    parts = [part for part in entry_header.split("/") if part]
    return parts[0] if len(parts) > 1 else Path(entry_header).stem


def _entry_name(entry_header: str) -> str:
    return Path(entry_header).stem


def _stem_matches_entry(stem: str, entry_name: str) -> bool:
    return (
        stem == entry_name
        or stem.startswith(f"{entry_name}.")
        or stem == f"{entry_name}_comp"
        or stem == f"{entry_name}.comp"
        or (entry_name == "swap" and stem == "swap_array")
    )


def _inferred_test_paths(test_index: CCCLTestIndexReport, entry_header: str) -> list[str]:
    module = _entry_module(entry_header)
    prefix = _TEST_DIRECTORY_PREFIX_BY_MODULE.get(module)
    if not prefix:
        return []
    name = _entry_name(entry_header)
    paths: list[str] = []
    for entry in test_index.tests:
        if not entry.relative_path.startswith(prefix):
            continue
        if _stem_matches_entry(_test_stem(entry.relative_path), name):
            paths.append(entry.relative_path)
    return sorted(paths)


def _candidate_test_paths(test_index: CCCLTestIndexReport, entry_header: str) -> list[str]:
    paths: set[str] = set(_mapped_test_paths(test_index, entry_header))
    paths.update(_inferred_test_paths(test_index, entry_header))
    return sorted(paths)


def _read_indexed_test_text(test_index: CCCLTestIndexReport, relative_path: str) -> str:
    path = Path(test_index.test_root) / relative_path
    return path.read_text(encoding="utf-8", errors="replace")


def _dependency_blockers(
    entry: CCCLTestIndexEntry,
    *,
    entry_header: str,
    dependency_status_by_header: dict[str, str] | None,
) -> list[str]:
    if not dependency_status_by_header:
        return []
    blocked: list[str] = []
    for header in entry.candidate_headers:
        if header == entry_header:
            continue
        if not header.startswith("__"):
            continue
        status = dependency_status_by_header.get(header, "pending")
        if status not in _SAFE_DEPENDENCY_STATUSES:
            blocked.append(f"{header}:{status}")
    return blocked


def plan_upstream_tests_for_header(
    test_index: CCCLTestIndexReport,
    *,
    entry_header: str,
    dependency_status_by_header: dict[str, str] | None = None,
    scaffold_inexpressible_tests: set[str] | None = None,
    max_selected_tests: int = 4,
) -> UpstreamTestPlan:
    """Select mapped upstream pass tests and explicitly defer the rest.

    The real CCCL layout does not mirror header paths, so Node 13 uses
    ``core.analysis.test_index`` mappings instead of fixture-style path guesses.
    """
    entries = _index_entries_by_path(test_index)
    selected: list[UpstreamTestDecision] = []
    deferred: list[UpstreamTestDecision] = []
    inexpressible = scaffold_inexpressible_tests or set()

    for relpath in _candidate_test_paths(test_index, entry_header):
        entry = entries.get(relpath)
        if entry is None:
            deferred.append(
                UpstreamTestDecision(relpath, "unknown", "deferred", "missing-index-entry", [])
            )
            continue

        blockers = _dependency_blockers(
            entry,
            entry_header=entry_header,
            dependency_status_by_header=dependency_status_by_header,
        )
        if entry.kind == "pass":
            if relpath in inexpressible:
                deferred.append(
                    UpstreamTestDecision(
                        relpath,
                        entry.kind,
                        "deferred",
                        "scaffold-inexpressible",
                        list(entry.candidate_headers),
                    )
                )
            elif blockers:
                deferred.append(
                    UpstreamTestDecision(
                        relpath,
                        entry.kind,
                        "deferred",
                        "dependency-blocked:" + ",".join(blockers),
                        list(entry.candidate_headers),
                    )
                )
            elif len(selected) < max_selected_tests:
                selected.append(
                    UpstreamTestDecision(
                        relpath,
                        entry.kind,
                        "selected",
                        "applicable-pass",
                        list(entry.candidate_headers),
                    )
                )
            else:
                deferred.append(
                    UpstreamTestDecision(
                        relpath,
                        entry.kind,
                        "deferred",
                        "selection-limit",
                        list(entry.candidate_headers),
                    )
                )
        elif entry.kind == "verify":
            deferred.append(
                UpstreamTestDecision(
                    relpath,
                    entry.kind,
                    "deferred",
                    "verify-deferred",
                    list(entry.candidate_headers),
                )
            )
        elif entry.kind == "fail":
            deferred.append(
                UpstreamTestDecision(
                    relpath,
                    entry.kind,
                    "deferred",
                    "compile-fail",
                    list(entry.candidate_headers),
                )
            )
        else:
            deferred.append(
                UpstreamTestDecision(
                    relpath,
                    entry.kind,
                    "deferred",
                    "unsupported-kind",
                    list(entry.candidate_headers),
                )
            )

    text_blocks: list[str] = []
    for decision in selected:
        text_blocks.append(
            f"// ===== upstream test: {decision.relative_path} ({decision.reason}) =====\n"
            + _read_indexed_test_text(test_index, decision.relative_path)
        )
    return UpstreamTestPlan(
        entry_header=entry_header,
        selected_tests=selected,
        deferred_tests=deferred,
        selected_test_text="\n\n".join(text_blocks),
    )


def _format_upstream_test_plan(plan: UpstreamTestPlan | None) -> str:
    if plan is None:
        return "未提供 real test-index mapping；本次使用 legacy 单测试文本。"
    lines = [f"entry_header: {plan.entry_header}", "selected_upstream_pass_tests:"]
    if plan.selected_tests:
        for item in plan.selected_tests:
            lines.append(f"- {item.relative_path} [{item.reason}]")
    else:
        lines.append("- <none>")
    lines.append("deferred_upstream_tests:")
    if plan.deferred_tests:
        for item in plan.deferred_tests:
            lines.append(f"- {item.relative_path} [{item.kind}; {item.reason}]")
    else:
        lines.append("- <none>")
    return "\n".join(lines)


def default_test_plan_filename(entry_header: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z_.-]+", "_", entry_header.strip().replace("/", "__"))
    safe = safe.strip("._") or "unknown"
    return f"test_migration_plan_{safe}.json"


def write_upstream_test_plan_report(
    plan: UpstreamTestPlan,
    output_dir: str | Path,
    *,
    filename: str | None = None,
    include_selected_test_text: bool = True,
) -> Path:
    name = Path(filename or default_test_plan_filename(plan.entry_header))
    if name.is_absolute() or len(name.parts) != 1:
        raise ValueError("test migration plan filename must be a file name under outputs/")
    path = Path(output_dir) / name
    payload = json.dumps(
        plan.to_dict(include_selected_test_text=include_selected_test_text),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    save_text(path, payload + "\n")
    return path


def _read_optional(path_str: str) -> str:
    try:
        return read_text_file(path_str)
    except FileNotFoundError:
        return ""


def _build_examples_block(config: Config, *, algo_name: str = "", cccl_test_text: str = "") -> str:
    # 按算子相关度从 examples/tests 检索最贴近的示例（默认开；关掉则用配置顺序）。
    selected = select_test_examples(
        config, algo_name=algo_name, cccl_test_text=cccl_test_text,
        k=config.few_shot_top_k, enabled=config.examples_retrieval_enabled,
        exclude_self=True,  # 迁 X 的测试不拿 X 自己的测试当示例（防泄漏）
    )
    blocks: list[str] = []
    for ex in selected:
        cccl_test = _read_optional(ex.get("cccl_test", ""))
        accl_host = _read_optional(ex.get("accl_host", ""))
        accl_kernel_spec = _read_optional(ex.get("accl_kernel_spec", ""))
        if not (cccl_test and accl_host and accl_kernel_spec):
            continue
        name = ex.get("name", "")
        blocks.append(
            f"""====================
【测试迁移示例 {name} —— CCCL 侧测试】
{cccl_test}

【测试迁移示例 {name} —— 正确的 ACCL host 测试】
{accl_host}

【测试迁移示例 {name} —— 正确的 ACCL kernel_spec(JSON)】
{accl_kernel_spec}
"""
        )
    return "\n".join(blocks)


def build_test_migration_request(
    *,
    algo_name: str,
    include_path: str,
    target_relpath: str,
    cccl_header_text: str,
    accl_header_text: str,
    cccl_test_text: str,
    examples_block: str,
    upstream_test_plan_text: str = "",
    knowledge_block: str = "",
) -> str:
    knowledge_section = f"\n{knowledge_block.strip()}\n" if knowledge_block.strip() else ""
    return f"""【algo_name】
{algo_name}

【include_path（host/kernel 测试里 include 的路径）】
{include_path}

【target_relpath（ACCL 头在仓库中的相对路径）】
{target_relpath}

【CCCL 头文件内容（语义参考）】
{cccl_header_text}

【已迁移好的 ACCL 头文件内容（真实可调用签名，以此为准）】
{accl_header_text}

【CCCL 侧测试代码（要迁移的用例来源）】
{cccl_test_text}

【real test-index 选择/延期计划】
{upstream_test_plan_text}
{knowledge_section}
{examples_block}
"""


_HOST_SYNTAX_REPAIR_SYSTEM = (
    "你是 ASC-STL host 测试修复助手。只修复给定 host 测试的编译/语法错误，"
    "保持用例语义不变。只输出 JSON 对象。"
)


def _host_syntax_check_passed(diag: str) -> bool:
    return diag.startswith("OK")


def _build_host_syntax_repair_request(host_code: str, diagnostics: str) -> str:
    return f"""【任务】修复下面这段 ACCL host 测试，使其能通过 g++ -fsyntax-only -std=c++17 编译。

【硬约束】
1. 只修编译/语法错误（如缺分号、声明位置、推导指引/模板写法），保持原有用例与断言语义不变。
2. 必须保留：任一用例失败时进程返回非零（例如累计 g_failures 后 return g_failures == 0 ? 0 : 1）。
3. expected/golden 不得调用 asc::std::*（保持独立参考实现）。
4. 若错误其实出在被包含的 asc/std 头（而非测试本身），在 notes 说明，不要臆改测试逻辑。
5. 只输出 JSON：{{"host_test_code": "<完整修复后的 .cpp>", "notes": "<改动说明>"}}。

【当前 host 测试】
{host_code}

【g++ -fsyntax-only 诊断】
{diagnostics}
"""


def ensure_host_test_compiles(
    model_client: BaseModelClient,
    host_code: str,
    *,
    toolbox,
    output_dir: Path,
    algo_name: str,
    rounds: int,
    verbose: bool = True,
    show_model_io: bool = False,
) -> tuple[str, dict]:
    """生成期强制 g++ 语法自检：失败则回灌模型修复，最多 ``rounds`` 轮（根本性兜底）。

    把「漏分号」这类编译错挡在生成阶段，而不是拖到 cmake/cannsim。无 toolbox / 无 g++ 时安全跳过
    （离线/mock 不受影响）。仅当诊断指向测试本身（snippet.cpp）才回灌——纯头依赖缺口不浪费模型调用。
    返回 (最终 host_code, 审计信息 dict)。
    """
    info: dict = {"checked": False, "passed": None, "attempts": 0}
    if toolbox is None or not hasattr(toolbox, "host_syntax_check") or rounds < 0:
        return host_code, info
    info["checked"] = True
    for attempt in range(rounds + 1):
        diag = toolbox.host_syntax_check(host_code)
        if _host_syntax_check_passed(diag):
            info.update(passed=True, attempts=attempt)
            return host_code, info
        if "未找到编译器" in diag:
            info.update(passed=None, no_compiler=True)
            return host_code, info
        info["last_diagnostics"] = diag[:1000]
        # 错误若不在测试本身（snippet.cpp）而在被包含的头 -> 测试改不了，交给下游测试反馈循环。
        if "snippet.cpp" not in diag:
            info.update(passed=False, attempts=attempt, header_side=True)
            return host_code, info
        if attempt >= rounds:
            info.update(passed=False, attempts=attempt)
            break
        if verbose:
            print(f"[host-syntax] {algo_name}: 第 {attempt + 1} 轮编译自检失败，回灌模型修复...")
        request = _build_host_syntax_repair_request(host_code, diag)
        save_text(output_dir / f"host_syntax_repair_{algo_name}_round{attempt + 1}.md", request)
        try:
            raw = call_model_with_io(
                model_client, stage=f"host 语法自检修复（{algo_name}）",
                system_prompt=_HOST_SYNTAX_REPAIR_SYSTEM, user_content=request, show_io=show_model_io,
            )
            data = extract_json_object(raw, strict=False)
            fixed = data.get("host_test_code")
            if not fixed or not str(fixed).strip():
                info["note"] = "模型未返回 host_test_code，停止修复"
                info.update(passed=False, attempts=attempt + 1)
                break
            host_code = validate_host_test_code(fixed, algo_name=algo_name)
        except Exception as exc:  # 单轮修复失败不应让整个测试迁移崩
            info["note"] = f"修复失败: {type(exc).__name__}: {exc}"
            info.update(passed=False, attempts=attempt + 1)
            break
    return host_code, info


def migrate_operator_tests(
    config: Config,
    model_client: BaseModelClient,
    *,
    algo_name: str,
    include_path: str,
    target_relpath: str,
    cccl_header_text: str,
    accl_header_text: str,
    cccl_test_text: str,
    test_index: CCCLTestIndexReport | None = None,
    entry_header: str = "",
    dependency_status_by_header: dict[str, str] | None = None,
    scaffold_inexpressible_tests: set[str] | None = None,
    prompt_filename: str = "migrate_tests.md",
    kernel_required: bool = True,
    verbose: bool = True,
    show_model_io: bool = False,
    toolbox=None,
    max_tool_rounds: int = 4,
) -> MigratedTests:
    """调模型，把 CCCL 测试迁移为 ACCL host 测试 + kernel_spec。

    toolbox 非空且客户端支持时，模型可先读 ACCL 头真实签名 / grep 符号 / g++ 自检
    host 测试，再产出迁移结果（生成期取证），否则回退「单轮 prompt→JSON」。
    """
    out = config.model_output_dir
    upstream_plan: UpstreamTestPlan | None = None
    if test_index is not None and entry_header:
        upstream_plan = plan_upstream_tests_for_header(
            test_index,
            entry_header=entry_header,
            dependency_status_by_header=dependency_status_by_header,
            scaffold_inexpressible_tests=scaffold_inexpressible_tests,
        )
        if upstream_plan.selected_test_text.strip():
            cccl_test_text = upstream_plan.selected_test_text
    examples_block = _build_examples_block(
        config, algo_name=algo_name, cccl_test_text=cccl_test_text
    )
    # 知识库注入：以已迁移 ACCL 头 + CCCL 测试为查询，命中符号映射/约束（如 double dtype）。
    knowledge_block = load_knowledge_base(str(config.reference_dir)).render_block(
        accl_header_text + "\n" + cccl_test_text
    )
    request_text = build_test_migration_request(
        algo_name=algo_name,
        include_path=include_path,
        target_relpath=target_relpath,
        cccl_header_text=cccl_header_text,
        accl_header_text=accl_header_text,
        cccl_test_text=cccl_test_text,
        examples_block=examples_block,
        upstream_test_plan_text=_format_upstream_test_plan(upstream_plan),
        knowledge_block=knowledge_block,
    )
    if not kernel_required:
        # host-only 头（类型特征/宏/host-stdlib）无设备算子：无需 kernel_spec。
        request_text += (
            "\n【kernel 适用性】\n"
            "本头被判定为 host-only（无设备侧算子）。无需生成 kernel_spec："
            "kernel_spec 可省略或留空，只需给出可编译、能在任一用例失败时返回非零的 host_test_code。\n"
        )
    save_text(out / "test_migrate_request.md", request_text)

    prompt_text = config.read_skill(prompt_filename)
    if verbose:
        tool_hint = "（带工具自检）" if toolbox is not None else ""
        print(f"开始调用模型迁移 {algo_name} 的测试代码{tool_hint}...")
    def _gen() -> str:
        return call_model_maybe_tools(
            model_client,
            stage=f"测试迁移（{algo_name}）",
            system_prompt=prompt_text,
            user_content=request_text,
            show_io=show_model_io,
            toolbox=toolbox,
            max_tool_rounds=max_tool_rounds,
            tool_log_tag=f"test_migrate_{algo_name}",
        )

    def _parse(text: str) -> dict:
        d = extract_json_object(text)
        raw_spec = d.get("kernel_spec", {})
        if kernel_required:
            kernel_spec = validate_kernel_spec(raw_spec)
        else:
            # host-only：kernel_spec 可选——给了且合法就保留，否则留空（不阻塞测试迁移）。
            try:
                kernel_spec = validate_kernel_spec(raw_spec) if raw_spec else {}
            except ValueError:
                kernel_spec = {}
        return {
            "host_test_code": validate_host_test_code(d.get("host_test_code", ""), algo_name=algo_name),
            "kernel_spec": kernel_spec,
            "notes": str(d.get("notes", "")).strip(),
        }

    # best-of-N：draft_samples>1 时多采样，host 测试以 g++ -fsyntax-only 自检择优（默认 1）。
    if config.draft_samples > 1:
        parsed, raw, scores = best_of_n(
            _gen, _parse,
            lambda p: score_host_test_code(p["host_test_code"], toolbox),
            n=config.draft_samples,
        )
        if verbose:
            print(f"best-of-{config.draft_samples} 测试迁移择优：scores={scores}")
    else:
        raw = _gen()
        parsed = _parse(raw)
    save_text(out / "test_migrate_raw.md", raw)

    host_test_code = parsed["host_test_code"]
    # 生成期强制 g++ 语法自检 + 失败回灌修复（根本性兜底；把漏分号这类编译错挡在源头）。
    host_test_code, syntax_info = ensure_host_test_compiles(
        model_client, host_test_code,
        toolbox=toolbox, output_dir=out, algo_name=algo_name,
        rounds=config.host_syntax_repair_rounds, verbose=verbose, show_model_io=show_model_io,
    )
    kernel_spec = parsed["kernel_spec"]
    notes = parsed["notes"]

    result = {
        "host_test_code": host_test_code.rstrip("\n"),
        "kernel_spec": kernel_spec,
        "notes": notes,
        "host_syntax_check": syntax_info,
        "upstream_test_plan": upstream_plan.to_dict() if upstream_plan else None,
    }
    save_text(out / "test_migrate_result.json", json.dumps(result, ensure_ascii=False, indent=2))
    return MigratedTests(
        algo_name=algo_name,
        host_test_code=host_test_code,
        kernel_spec=kernel_spec,
        notes=notes,
        upstream_test_plan=upstream_plan,
    )
