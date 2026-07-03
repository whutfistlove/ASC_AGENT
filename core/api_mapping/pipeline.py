"""Resumable, evidence-backed CCCL CUDA API mapping pipeline.

The LLM performs semantic extraction and matching.  Deterministic code owns the
inventory, declaration-candidate checklist, documentation retrieval, schema
validation, path validation, resume state, and final report.  This separation
is deliberate: a fluent model answer must never be mistaken for full coverage.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import sys
import traceback
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from difflib import get_close_matches
from pathlib import Path
from typing import Any, Callable

from core.llm.model_client import extract_json_object


PIPELINE_VERSION = "5"
# Scope-only revisions of the extraction skill remain compatible because the
# deterministic validator/report filter enforces the tightened rules on old
# checkpoints. Keeping this explicit avoids silently accepting arbitrary skill
# changes while preserving completed model work.
_COMPATIBLE_SKILL_SHA256 = {
    "11cf069e2857ebfdb742edf3292e31ce0d9bebc803f15b0c39564055328440bb",
    "7ed5cfaf10c5700620f8490749d401260e455240db5b3f31c4e54211e6f5bed4",
}
VALID_KINDS = {"function", "method", "constructor", "operator", "type", "alias", "concept", "variable", "other"}
VALID_DEVICE_SUPPORT = {"device", "host_device", "compile_time", "host_only", "unknown"}
VALID_VISIBILITY = {"public", "internal", "implementation"}
VALID_API_ORIGINS = {"referenced"}
VALID_MATCH = {"exact", "partial", "semantic", "uncertain", "no_match"}

_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)
_CODE_TOKEN_RE = re.compile(r"`([^`\n]{1,160})`|\[([^\]\n]{1,160})\]\([^)]*\)")
_CONTROL_WORDS = {"if", "for", "while", "switch", "return", "sizeof", "alignof", "decltype", "requires", "static_assert", "defined"}
_CUDA_ENUM_VALUE_RE = re.compile(r"^(?:CU|CUDA)_[A-Z][A-Z0-9_]*$")
_CUDA_RUNTIME_STATUS_RE = re.compile(r"^cuda(?:Success|Error[A-Z][A-Za-z0-9_]*)$")
_CUDA_RUNTIME_DRIVER_TYPE_RE = re.compile(r"^(?:cuda|CU)[A-Za-z0-9_]*$")
_INTERNAL_ACCESS_ENUM_VALUES = {"__host", "__device", "__host_device"}
_CUDA_DEVICE_BUILTIN_VARIABLES = {"threadIdx", "blockIdx", "blockDim", "gridDim", "warpSize"}

# Retrieval routing is intentionally small and auditable.  It only broadens
# candidate recall; the model still has to prove semantic correspondence.
_CATEGORY_HINTS: dict[str, tuple[str, ...]] = {
    "atomic": ("原子", "atomic"),
    "barrier": ("同步", "栅栏", "barrier", "fence"),
    "semaphore": ("同步", "信号量", "semaphore"),
    "warp": ("warp", "线程束", "协作组", "shfl", "ballot"),
    "cooperative": ("协作组", "thread_block", "coalesced", "tiled"),
    "cmath": ("数学函数", "math"),
    "math": ("数学函数", "math"),
    "fp16": ("half", "fp16", "半精度"),
    "fp8": ("fp8", "hif8", "e4m3", "e5m2"),
    "memory": ("内存", "地址空间", "memory"),
    "bit": ("整型数学", "位反转", "__brev", "popc"),
    "ptx": ("指令", "内建", "intrinsic", "ptx"),
    "complex": ("复数", "complex"),
    "random": ("随机", "random"),
}


def _normal_api_name(name: Any) -> str:
    return str(name or "").strip().removeprefix("::")


def _is_package_internal_api_name(name: Any) -> bool:
    """Return true for libcudacxx APIs that will migrate through dependency closure.

    The mapping report is meant to list platform APIs that need an Ascend SIMT
    counterpart.  Names rooted at cuda:: / cuda::std:: are implemented inside
    the same source package under include/cuda, so they are dependency edges,
    not replacement targets for this pipeline.
    """

    normalized = _normal_api_name(name)
    return normalized.startswith("cuda::")


def _skill_hash_is_compatible(checkpoint_hash: Any, current_hash: str) -> bool:
    value = str(checkpoint_hash or "")
    return value == current_hash or value in _COMPATIBLE_SKILL_SHA256


def _api_exclusion_reason(api: dict, locally_declared_names: set[str] | None = None) -> str | None:
    """Explain why a model-extracted symbol is not a replacement target."""

    name = _normal_api_name(api.get("name"))
    if _is_package_internal_api_name(name):
        return "libcudacxx 包内依赖"
    if name.split("::")[-1] in (locally_declared_names or set()):
        return "当前头文件自身声明/定义的包内符号"
    if api.get("kind") in {"type", "alias"} and _CUDA_RUNTIME_DRIVER_TYPE_RE.fullmatch(name):
        return "CUDA runtime/driver 句柄、配置或枚举类型"

    # The model occasionally shortens a qualified member such as
    # ::cuda::std::numeric_limits<T>::max() to just `max`.  Its observed
    # signature retains the ownership information and is more reliable than
    # the shortened name.
    signature = str(api.get("signature") or "")
    if re.search(r"(?<![A-Za-z0-9_])(?:::)?cuda::", signature):
        return "签名属于 libcudacxx 包内依赖"

    # These are values, not callable/type APIs that need a SIMT replacement.
    # Keep device built-in variables (for example threadIdx) eligible; only
    # reject well-known CUDA/driver enum-value spellings here.
    if name in _INTERNAL_ACCESS_ENUM_VALUES:
        return "libcudacxx 内存可访问性枚举值"
    if _CUDA_ENUM_VALUE_RE.fullmatch(name) or _CUDA_RUNTIME_STATUS_RE.fullmatch(name):
        return "CUDA 运行时/驱动枚举值或状态常量"
    if api.get("kind") == "variable" and name.split("::")[-1] not in _CUDA_DEVICE_BUILTIN_VARIABLES:
        return "普通常量或枚举值（非 CUDA 设备内置变量）"
    return None


def _is_reportable_api(api: dict, locally_declared_names: set[str] | None = None) -> bool:
    return _api_exclusion_reason(api, locally_declared_names) is None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_text(text: str) -> str:
    return _sha256_bytes(text.encode("utf-8"))


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(path)


def _safe_relpath(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _json_marker(text: str, marker: str) -> Any:
    """Read a compact JSON line following a marker (used by the mock client)."""
    match = re.search(rf"^{re.escape(marker)}\s*(.+)$", text, re.MULTILINE)
    return json.loads(match.group(1)) if match else None


@dataclass
class ApiMappingOptions:
    source_root: Path
    docs_root: Path
    output_dir: Path
    skill_path: Path
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    limit: int = 0
    max_source_chars: int = 32_000
    source_overlap_lines: int = 24
    max_apis_per_mapping_call: int = 10
    top_docs_per_api: int = 4
    max_docs_per_mapping_call: int = 32
    max_doc_chars: int = 2_800
    model_retries: int = 2
    resume: bool = True
    retry_failed: bool = False
    fail_fast: bool = False
    show_model_io: bool = False
    save_model_io: bool = True

    def validate(self) -> None:
        if not self.source_root.is_dir():
            raise FileNotFoundError(f"CCCL CUDA include root 不存在: {self.source_root}")
        if not self.docs_root.is_dir():
            raise FileNotFoundError(f"晟腾 SIMT 文档目录不存在: {self.docs_root}")
        if not self.skill_path.is_file():
            raise FileNotFoundError(f"API mapping skill 不存在: {self.skill_path}")
        if self.max_source_chars < 4_000:
            raise ValueError("max_source_chars 必须 >= 4000")
        if self.source_overlap_lines < 0:
            raise ValueError("source_overlap_lines 必须 >= 0")
        if self.max_apis_per_mapping_call < 1 or self.top_docs_per_api < 1:
            raise ValueError("mapping batch size / top docs 必须 >= 1")


class DeterministicApiMappingMockClient:
    """Offline orchestration smoke client; it deliberately claims no APIs."""

    def generate(self, *, system_prompt: str, user_content: str, on_delta=None) -> str:
        candidates = _json_marker(user_content, "CANDIDATES_JSON:")
        if candidates is not None:
            coverage = [
                {"candidate_id": row["candidate_id"], "disposition": "non_api", "api_ids": [], "reason": "mock smoke classification"}
                for row in candidates
            ]
            return json.dumps({"apis": [], "coverage": coverage, "chunk_notes": "mock"}, ensure_ascii=False)
        apis = _json_marker(user_content, "SOURCE_APIS_JSON:") or []
        return json.dumps(
            {"mappings": [
                {"source_api_id": api["source_api_id"], "accl_apis": [], "match_status": "no_match", "doc_paths": [], "doc_evidence": [], "mapping_notes": "mock", "function_summary": api.get("summary", "")}
                for api in apis
            ]},
            ensure_ascii=False,
        )


@dataclass
class _SourceShard:
    index: int
    start_line: int
    end_line: int
    text: str


@dataclass
class _DocEntry:
    relative_path: str
    title: str
    headings: list[str]
    symbols: list[str]
    text: str = field(repr=False)

    def public_dict(self, include_text: bool = False) -> dict:
        out = {
            "relative_path": self.relative_path,
            "title": self.title,
            "headings": self.headings,
            "symbols": self.symbols,
        }
        if include_text:
            out["text"] = self.text
        return out


class _DocIndex:
    def __init__(self, root: Path, entries: list[_DocEntry], fingerprint: str):
        self.root = root
        self.entries = entries
        self.fingerprint = fingerprint
        self.by_path = {entry.relative_path: entry for entry in entries}

    @classmethod
    def build(cls, root: Path) -> "_DocIndex":
        entries: list[_DocEntry] = []
        fingerprint_rows: list[str] = []
        for path in sorted((p for p in root.rglob("*.md") if p.is_file()), key=lambda p: p.as_posix()):
            raw = path.read_bytes()
            text = raw.decode("utf-8", errors="replace")
            rel = _safe_relpath(path, root)
            headings = [re.sub(r"\s+", " ", value).strip() for value in _HEADING_RE.findall(text)]
            title = headings[0] if headings else path.stem
            symbols: set[str] = {path.stem}
            for left, right in _CODE_TOKEN_RE.findall(text):
                token = (left or right).strip()
                for ident in _IDENTIFIER_RE.findall(token):
                    if len(ident) > 1:
                        symbols.add(ident)
            entries.append(_DocEntry(rel, title, headings[:24], sorted(symbols), text))
            fingerprint_rows.append(f"{rel}:{_sha256_bytes(raw)}")
        return cls(root, entries, _sha256_text("\n".join(fingerprint_rows)))

    def catalog(self) -> dict:
        return {
            "docs_root": str(self.root.resolve()),
            "fingerprint": self.fingerprint,
            "document_count": len(self.entries),
            "documents": [entry.public_dict() for entry in self.entries],
        }

    def search(self, api: dict, source_relpath: str, limit: int) -> list[tuple[int, _DocEntry]]:
        name = str(api.get("unqualified_name") or api.get("name") or "").split("::")[-1]
        query_text = " ".join((name, str(api.get("name", "")), str(api.get("summary", "")), source_relpath))
        terms = {t.lower() for t in _IDENTIFIER_RE.findall(query_text) if len(t) > 1 and t.lower() not in {"cuda", "std", "detail"}}
        normalized_name = name.lower().lstrip("_")
        route_hints: set[str] = set()
        lower_query = query_text.lower()
        for key, hints in _CATEGORY_HINTS.items():
            if key in lower_query:
                route_hints.update(hints)

        scored: list[tuple[int, str, _DocEntry]] = []
        for entry in self.entries:
            title_path = f"{entry.title} {entry.relative_path}".lower()
            haystack = f"{title_path} {' '.join(entry.symbols)} {entry.text}".lower()
            entry_names = {s.lower().lstrip("_") for s in entry.symbols}
            score = 0
            if normalized_name and normalized_name in entry_names:
                score += 180
            if name and name.lower() in title_path:
                score += 110
            if normalized_name and re.search(rf"(?<![a-z0-9_]){re.escape(normalized_name)}[fl]?(?![a-z0-9_])", haystack):
                score += 70
            for term in terms:
                if term in title_path:
                    score += 18
                elif term in haystack:
                    score += 3
            score += 12 * sum(1 for hint in route_hints if hint.lower() in title_path)
            if score > 0:
                scored.append((score, entry.relative_path, entry))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [(score, entry) for score, _, entry in scored[:limit]]


class ApiMappingPipeline:
    def __init__(self, options: ApiMappingOptions, model_client, *, model_name: str = "unknown"):
        options.validate()
        self.options = options
        self.model = model_client
        self.model_name = model_name
        self.skill_text = options.skill_path.read_text(encoding="utf-8")
        self.skill_hash = _sha256_text(self.skill_text)
        self.results_dir = options.output_dir / "files"
        self.io_dir = options.output_dir / "model_io"
        self._all_inventory: list[dict] = []

    def prepare(self) -> tuple[list[dict], _DocIndex]:
        inventory = self._source_inventory()
        docs = _DocIndex.build(self.options.docs_root)
        _atomic_json(self.options.output_dir / "source_inventory.json", {
            "pipeline_version": PIPELINE_VERSION,
            "generated_at": _utc_now(),
            "source_root": str(self.options.source_root.resolve()),
            "file_count": len(self._all_inventory),
            "selected_file_count": len(inventory),
            "selected_relative_paths": [row["relative_path"] for row in inventory],
            "files": self._all_inventory,
        })
        _atomic_json(self.options.output_dir / "docs_index.json", docs.catalog())
        return inventory, docs

    def run(self, *, prepare_only: bool = False) -> dict:
        inventory, docs = self.prepare()
        if prepare_only:
            summary = self.render(inventory, docs)
            summary["prepare_only"] = True
            return summary

        attempted = skipped = succeeded = failed = 0
        for row in inventory:
            result_path = self._result_path(row["relative_path"])
            previous = self._read_json(result_path)
            if self._can_resume(previous, row, docs):
                skipped += 1
                continue
            failed_is_current = bool(
                previous
                and previous.get("status") == "failed"
                and previous.get("pipeline_version") == PIPELINE_VERSION
                and previous.get("source_sha256") == row["sha256"]
                and previous.get("docs_fingerprint") == docs.fingerprint
                and _skill_hash_is_compatible(previous.get("skill_sha256"), self.skill_hash)
                and previous.get("model_name") == self.model_name
            )
            if failed_is_current and not self.options.retry_failed and self.options.resume:
                skipped += 1
                continue
            attempted += 1
            try:
                result = self._analyze_file(row, docs)
                succeeded += 1
            except Exception as exc:
                failed += 1
                result = {
                    "pipeline_version": PIPELINE_VERSION,
                    "status": "failed",
                    "source_file": row["relative_path"],
                    "source_sha256": row["sha256"],
                    "docs_fingerprint": docs.fingerprint,
                    "skill_sha256": self.skill_hash,
                    "model_name": self.model_name,
                    "updated_at": _utc_now(),
                    "error": f"{type(exc).__name__}: {exc}",
                    "traceback": traceback.format_exc(limit=8),
                }
                if self.options.fail_fast:
                    _atomic_json(result_path, result)
                    self.render(inventory, docs)
                    raise
            _atomic_json(result_path, result)
            self.render(inventory, docs)
            print(f"[api-map] {row['relative_path']}: {result['status']}")

        summary = self.render(inventory, docs)
        summary.update({"attempted": attempted, "resumed": skipped, "succeeded_this_run": succeeded, "failed_this_run": failed})
        return summary

    def _source_inventory(self) -> list[dict]:
        all_rows: list[dict] = []
        for path in sorted((p for p in self.options.source_root.rglob("*") if p.is_file()), key=lambda p: p.as_posix()):
            rel = _safe_relpath(path, self.options.source_root)
            raw = path.read_bytes()
            if b"\x00" in raw:
                continue
            all_rows.append({
                "relative_path": rel,
                "layer": "cuda_std" if rel == "std" or rel.startswith("std/") else "cuda_extension",
                "size_bytes": len(raw),
                "line_count": raw.count(b"\n") + (0 if not raw or raw.endswith(b"\n") else 1),
                "sha256": _sha256_bytes(raw),
            })
        rows = [
            row for row in all_rows
            if (not self.options.include or any(fnmatch.fnmatch(row["relative_path"], pattern) for pattern in self.options.include))
            and not any(fnmatch.fnmatch(row["relative_path"], pattern) for pattern in self.options.exclude)
        ]
        if self.options.limit > 0:
            rows = rows[: self.options.limit]
        if not rows:
            paths = [row["relative_path"] for row in all_rows]
            suggestions: list[str] = []
            for pattern in self.options.include:
                literal = pattern.replace("*", "").replace("?", "")
                basename = Path(literal).name
                suggestions.extend(path for path in paths if Path(path).name == basename)
                suggestions.extend(get_close_matches(literal, paths, n=3, cutoff=0.45))
            suggestions = list(dict.fromkeys(suggestions))[:8]
            detail = f"；可能想要: {', '.join(suggestions)}" if suggestions else ""
            raise ValueError(
                "源文件筛选结果为 0，未调用模型。"
                f" include={list(self.options.include)}, exclude={list(self.options.exclude)}{detail}"
            )
        self._all_inventory = all_rows
        return rows

    def _result_path(self, relpath: str) -> Path:
        stable = hashlib.sha1(relpath.encode("utf-8")).hexdigest()[:16]
        return self.results_dir / f"{stable}.json"

    @staticmethod
    def _read_json(path: Path) -> dict | None:
        if not path.exists():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else None
        except (OSError, json.JSONDecodeError):
            return None

    def _can_resume(self, previous: dict | None, row: dict, docs: _DocIndex) -> bool:
        return bool(
            self.options.resume
            and previous
            and previous.get("status") == "completed"
            and previous.get("pipeline_version") == PIPELINE_VERSION
            and previous.get("source_sha256") == row["sha256"]
            and previous.get("docs_fingerprint") == docs.fingerprint
            and _skill_hash_is_compatible(previous.get("skill_sha256"), self.skill_hash)
            and previous.get("model_name") == self.model_name
        )

    def _analyze_file(self, row: dict, docs: _DocIndex) -> dict:
        source_path = self.options.source_root / row["relative_path"]
        source_text = source_path.read_text(encoding="utf-8", errors="replace")
        file_candidates = _candidate_anchors(source_text, 1, 0)
        locally_declared_names = _locally_declared_names(file_candidates)
        shards = _split_source(source_text, self.options.max_source_chars, self.options.source_overlap_lines)
        extracted: list[dict] = []
        coverage_rows: list[dict] = []
        candidate_total = 0
        for shard in shards:
            numbered = _number_lines(shard.text, shard.start_line)
            candidates = _candidate_anchors(shard.text, shard.start_line, shard.index)
            candidate_total += len(candidates)
            user = self._extraction_request(row["relative_path"], shard, numbered, candidates)
            payload = self._call_validated(
                stage=f"extract:{row['relative_path']}:{shard.index}",
                user=user,
                validator=lambda obj, candidates=candidates: _validate_extraction(
                    obj, candidates, shard, locally_declared_names
                ),
                io_tag=f"{self._result_path(row['relative_path']).stem}/extract-{shard.index:04d}",
            )
            for api in payload["apis"]:
                api["source_shard"] = shard.index
            extracted.extend(payload["apis"])
            coverage_rows.extend(payload["coverage"])

        apis = _deduplicate_apis(extracted)
        mappings: list[dict] = []
        for offset in range(0, len(apis), self.options.max_apis_per_mapping_call):
            batch = apis[offset : offset + self.options.max_apis_per_mapping_call]
            candidates_by_api, selected_docs = self._mapping_documents(batch, row["relative_path"], docs)
            for api in batch:
                api["documentation_candidates"] = candidates_by_api.get(api["source_api_id"], [])
            user = self._mapping_request(row["relative_path"], batch, candidates_by_api, selected_docs)
            payload = self._call_validated(
                stage=f"map:{row['relative_path']}:{offset // self.options.max_apis_per_mapping_call + 1}",
                user=user,
                validator=lambda obj, batch=batch, docs=docs, allowed_by_api={
                    api_id: {row["path"] for row in rows}
                    for api_id, rows in candidates_by_api.items()
                }: _validate_mappings(obj, batch, docs, allowed_by_api),
                io_tag=f"{self._result_path(row['relative_path']).stem}/map-{offset // self.options.max_apis_per_mapping_call + 1:04d}",
            )
            mappings.extend(payload["mappings"])
        mapping_by_id = {m["source_api_id"]: m for m in mappings}
        final_apis = [{**api, **mapping_by_id[api["source_api_id"]]} for api in apis]
        return {
            "pipeline_version": PIPELINE_VERSION,
            "status": "completed",
            "source_file": row["relative_path"],
            "source_layer": row["layer"],
            "source_sha256": row["sha256"],
            "source_size_bytes": row["size_bytes"],
            "source_line_count": row["line_count"],
            "docs_fingerprint": docs.fingerprint,
            "skill_sha256": self.skill_hash,
            "model_name": self.model_name,
            "updated_at": _utc_now(),
            "shard_count": len(shards),
            "candidate_count": candidate_total,
            "coverage_count": len(coverage_rows),
            "coverage_complete": len(coverage_rows) == candidate_total,
            "api_count": len(final_apis),
            "apis": final_apis,
        }

    def _mapping_documents(self, batch: list[dict], source_relpath: str, docs: _DocIndex) -> tuple[dict[str, list[dict]], dict[str, _DocEntry]]:
        hits_by_api = {
            api["source_api_id"]: docs.search(api, source_relpath, self.options.top_docs_per_api)
            for api in batch
        }
        selected: dict[str, _DocEntry] = {}
        # Round-robin selection prevents the first APIs in a batch from consuming
        # the global document budget and starving later APIs.
        for rank in range(self.options.top_docs_per_api):
            for api in batch:
                hits = hits_by_api[api["source_api_id"]]
                if rank >= len(hits):
                    continue
                _, entry = hits[rank]
                if entry.relative_path in selected:
                    continue
                if len(selected) >= self.options.max_docs_per_mapping_call:
                    continue
                selected[entry.relative_path] = entry
        allowed = set(selected)
        per_api = {
            api_id: [
                {"path": entry.relative_path, "score": score}
                for score, entry in hits
                if entry.relative_path in allowed
            ]
            for api_id, hits in hits_by_api.items()
        }
        return per_api, selected

    def _extraction_request(self, relpath: str, shard: _SourceShard, numbered: str, candidates: list[dict]) -> str:
        schema = {
            "apis": [{"api_id": "local id", "name": "qualified external API name", "unqualified_name": "name", "kind": "function|method|constructor|operator|type|alias|concept|variable|other", "origin": "referenced", "signature": "observed call/use form", "source_line_start": 1, "source_line_end": 1, "device_support": "device|host_device|compile_time|host_only|unknown", "visibility": "public", "summary": "Chinese summary", "evidence": "source fragment", "candidate_ids": ["S001-C001"]}],
            "coverage": [{"candidate_id": "S001-C001", "disposition": "api|non_api|duplicate|conditional", "api_ids": ["local id"], "reason": "reason"}],
            "chunk_notes": "optional",
        }
        return (
            "STAGE: source_api_extraction\n"
            f"SOURCE_FILE: {relpath}\nSOURCE_SHARD: {shard.index}\nLINE_RANGE: {shard.start_line}-{shard.end_line}\n"
            f"OUTPUT_SCHEMA: {json.dumps(schema, ensure_ascii=False)}\n"
            "SCOPE_RULE: Only output external CUDA/NV platform APIs that need SIMT-side replacement. "
            "Treat names rooted at ::cuda:: or ::cuda::std:: as libcudacxx package-internal dependencies; "
            "mark their candidates non_api and never place them in apis. Preserve the fully qualified owner in name/signature; "
            "symbols declared or defined by the analyzed header itself are also package-internal and non_api. "
            "an unqualified member such as max/lowest from cuda::std is still non_api. CUDA/driver enum values, status constants "
            "(for example cudaSuccess or CU_MEMORYTYPE_HOST), and libcudacxx access enum members "
            "(__host/__device/__host_device) are values rather than mapping APIs; mark them non_api. Other ordinary constants "
            "and enum members are also non_api; CUDA device built-in variables such as threadIdx/blockIdx remain in scope. "
            "External public host-only CUDA runtime/driver functions remain in scope; output them with device_support=host_only. "
            "Runtime/driver types named cuda* or CU* (handles, structs, configuration/query types, and enum types) are non_api "
            "even if annotated host_device. Device-callable data types such as __half remain in scope.\n"
            f"CANDIDATES_JSON: {json.dumps(candidates, ensure_ascii=False)}\n"
            "NUMBERED_SOURCE_BEGIN\n" + numbered + "\nNUMBERED_SOURCE_END\n"
        )

    def _mapping_request(self, relpath: str, batch: list[dict], candidates_by_api: dict, selected_docs: dict[str, _DocEntry]) -> str:
        source_apis = [{k: v for k, v in api.items() if k not in {"candidate_ids", "source_shard", "documentation_candidates"}} for api in batch]
        docs_payload = [
            {
                "path": path,
                "title": entry.title,
                "headings": entry.headings,
                "symbols": entry.symbols,
                "text": entry.text[: self.options.max_doc_chars],
            }
            for path, entry in selected_docs.items()
        ]
        schema = {"mappings": [{"source_api_id": "API000001", "accl_apis": ["asc_api"], "match_status": "exact|partial|semantic|uncertain|no_match", "doc_paths": ["relative/doc.md"], "doc_evidence": ["brief evidence"], "mapping_notes": "differences", "function_summary": "Chinese summary"}]}
        return (
            "STAGE: documentation_mapping\n"
            f"SOURCE_FILE: {relpath}\nOUTPUT_SCHEMA: {json.dumps(schema, ensure_ascii=False)}\n"
            f"SOURCE_APIS_JSON: {json.dumps(source_apis, ensure_ascii=False)}\n"
            f"RETRIEVAL_BY_API_JSON: {json.dumps(candidates_by_api, ensure_ascii=False)}\n"
            f"DOCUMENT_CANDIDATES_JSON: {json.dumps(docs_payload, ensure_ascii=False)}\n"
        )

    def _call_validated(self, *, stage: str, user: str, validator: Callable[[dict], dict], io_tag: str) -> dict:
        errors: list[str] = []
        for attempt in range(1, self.options.model_retries + 2):
            retry_note = "" if not errors else f"\nPREVIOUS_VALIDATION_ERROR: {errors[-1]}\nCorrect the complete JSON response."
            full_user = user + retry_note
            raw = self._model_call(stage, full_user)
            if self.options.save_model_io:
                base = self.io_dir / io_tag
                _atomic_text(base.with_name(base.name + f"-request-{attempt}.md"), full_user)
                _atomic_text(base.with_name(base.name + f"-response-{attempt}.json"), raw)
            try:
                return validator(extract_json_object(raw, strict=True))
            except Exception as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
        raise ValueError(f"模型输出连续校验失败 ({stage}): {' | '.join(errors)}")

    def _model_call(self, stage: str, user: str) -> str:
        if not self.options.show_model_io:
            return self.model.generate(system_prompt=self.skill_text, user_content=user)
        sep = "=" * 72
        print(f"\n{sep}\n[API mapping] {stage} request\n{sep}\n{user}\n{sep}\nresponse\n{sep}")
        streamed = {"value": False}

        def on_delta(value: str) -> None:
            streamed["value"] = True
            sys.stdout.write(value)
            sys.stdout.flush()

        raw = self.model.generate(system_prompt=self.skill_text, user_content=user, on_delta=on_delta)
        if not streamed["value"]:
            print(raw)
        print(f"\n{sep}")
        return raw

    def render(self, inventory: list[dict], docs: _DocIndex) -> dict:
        results: list[dict] = []
        master_inventory = self._all_inventory or inventory
        for row in master_inventory:
            value = self._read_json(self._result_path(row["relative_path"]))
            if value and self._result_is_current(value, row, docs):
                results.append(value)
        # Per-file JSON is the resumable analysis checkpoint and remains
        # untouched. Project old checkpoints through the current reporting
        # filter so tightening scope does not force costly model re-analysis.
        projected_results: list[dict] = []
        for result in results:
            if result.get("status") != "completed":
                projected_results.append(result)
                continue
            source_path = self.options.source_root / str(result.get("source_file") or "")
            locally_declared_names: set[str] = set()
            if source_path.is_file():
                source_text = source_path.read_text(encoding="utf-8", errors="replace")
                locally_declared_names = _locally_declared_names(_candidate_anchors(source_text, 1, 0))
            visible_apis = [
                api
                for api in result.get("apis", [])
                if _is_reportable_api(api, locally_declared_names)
            ]
            projected_results.append({**result, "apis": visible_apis, "api_count": len(visible_apis)})
        completed = [r for r in projected_results if r.get("status") == "completed"]
        failed = [r for r in projected_results if r.get("status") == "failed"]
        apis = [api for result in completed for api in result.get("apis", [])]
        match_counts = Counter(api.get("match_status", "unknown") for api in apis)
        summary = {
            "pipeline_version": PIPELINE_VERSION,
            "generated_at": _utc_now(),
            "source_root": str(self.options.source_root.resolve()),
            "docs_root": str(self.options.docs_root.resolve()),
            "docs_fingerprint": docs.fingerprint,
            "inventory_files": len(master_inventory),
            "selected_files": len(inventory),
            "completed_files": len(completed),
            "failed_files": len(failed),
            "pending_files": max(0, len(master_inventory) - len(completed) - len(failed)),
            "api_count": len(apis),
            "match_counts": dict(sorted(match_counts.items())),
            "inventory": master_inventory,
            "results": sorted(projected_results, key=lambda r: r.get("source_file", "")),
        }
        _atomic_json(self.options.output_dir / "api_mapping.json", summary)
        _atomic_text(self.options.output_dir / "api_mapping.md", _render_markdown(summary))
        return {k: v for k, v in summary.items() if k not in {"results", "inventory"}}

    def _result_is_current(self, value: dict, row: dict, docs: _DocIndex) -> bool:
        """Keep the cumulative report free of stale source/docs/skill results."""
        return bool(
            value.get("pipeline_version") == PIPELINE_VERSION
            and value.get("source_file") == row["relative_path"]
            and value.get("source_sha256") == row["sha256"]
            and value.get("docs_fingerprint") == docs.fingerprint
            and _skill_hash_is_compatible(value.get("skill_sha256"), self.skill_hash)
        )


def _split_source(text: str, max_chars: int, overlap_lines: int) -> list[_SourceShard]:
    lines = text.splitlines(keepends=True)
    if not lines:
        return [_SourceShard(1, 1, 1, "")]
    shards: list[_SourceShard] = []
    start = 0
    while start < len(lines):
        end = start
        size = 0
        while end < len(lines) and (size + len(lines[end]) <= max_chars or end == start):
            size += len(lines[end])
            end += 1
        shards.append(_SourceShard(len(shards) + 1, start + 1, end, "".join(lines[start:end])))
        if end >= len(lines):
            break
        next_start = max(start + 1, end - overlap_lines)
        start = next_start
    return shards


def _number_lines(text: str, start_line: int) -> str:
    return "".join(f"{number:7d} | {line}" for number, line in enumerate(text.splitlines(keepends=True), start_line))


def _candidate_anchors(text: str, start_line: int, shard_index: int) -> list[dict]:
    candidates: list[dict] = []
    seen: set[tuple[int, str, str]] = set()
    patterns = [
        ("type", re.compile(r"\b(?:class|struct|union|enum(?:\s+class)?)\s+([A-Za-z_]\w*)")),
        ("concept", re.compile(r"\bconcept\s+([A-Za-z_]\w*)\s*=")),
        ("alias", re.compile(r"\busing\s+([A-Za-z_]\w*)\s*=")),
        ("alias", re.compile(r"\btypedef\b[^;{}()]*\b([A-Za-z_]\w*)\s*;")),
        ("api_reference", re.compile(r"(?<![A-Za-z0-9_>])((?:::)(?:[A-Za-z_]\w*::)*[A-Za-z_]\w*)\s*(?:<[^(){};]*>)?\s*\(")),
        ("api_reference", re.compile(r"(?<![A-Za-z0-9_:>])((?:::)(?:[A-Za-z_]\w*::)*__[A-Za-z_]\w*)\b")),
        ("function", re.compile(r"(?<![\w:])((?:operator\s*[^\s(]+)|(?:~?[A-Za-z_]\w*))\s*\(")),
        ("variable", re.compile(r"\b(?:constexpr|constinit)\b[^;{}()]*?\b([A-Za-z_]\w*)\s*(?:=|;)")),
    ]
    for offset, raw_line in enumerate(text.splitlines(), start_line):
        line = re.sub(r"//.*$", "", raw_line)
        for kind, pattern in patterns:
            for match in pattern.finditer(line):
                name = match.group(1).strip()
                if kind in {"function", "api_reference"}:
                    name = re.sub(r"\s*\($", "", name).strip()
                    if name in _CONTROL_WORDS or line.lstrip().startswith("#"):
                        continue
                key = (offset, kind, name)
                if key in seen:
                    continue
                seen.add(key)
                candidates.append({"candidate_id": "", "line": offset, "kind_hint": kind, "name_hint": name, "source": raw_line.strip()[:280]})
    candidates.sort(key=lambda row: (row["line"], row["kind_hint"], row["name_hint"]))
    declared_names = {
        row["name_hint"].split("::")[-1]
        for row in candidates
        if row["kind_hint"] == "function"
        and re.search(r"\b(?:_CCCL_API|_CCCL_DEVICE_API|_LIBCUDACXX_HIDE_FROM_ABI)\b", row["source"])
    }
    for row in candidates:
        row["must_be_api"] = False
        if row["kind_hint"] != "api_reference":
            continue
        qualified = row["name_hint"]
        final_name = qualified.split("::")[-1]
        row["scope_hint"] = "package_internal_dependency" if _is_package_internal_api_name(qualified) else "unknown"
        is_self_or_internal = (
            qualified.startswith("::cuda::") and final_name in declared_names
        ) or final_name.startswith(("__cccl", "__builtin"))
        is_global_call = qualified.startswith("::") and qualified.count("::") == 1
        if is_global_call and not is_self_or_internal:
            row["scope_hint"] = "external_global_cuda_api"
        row["must_be_api"] = bool(not _is_package_internal_api_name(qualified) and not is_self_or_internal and is_global_call)
    for index, row in enumerate(candidates, 1):
        row["candidate_id"] = f"S{shard_index:04d}-C{index:04d}"
    return candidates


def _locally_declared_names(candidates: list[dict]) -> set[str]:
    """Return symbols owned by the analyzed header rather than the platform."""

    names = {
        row["name_hint"].split("::")[-1]
        for row in candidates
        if row.get("kind_hint") in {"type", "alias", "concept"}
    }
    names.update(
        row["name_hint"].split("::")[-1]
        for row in candidates
        if row.get("kind_hint") == "function"
        and re.search(r"\b(?:_CCCL_API|_CCCL_DEVICE_API|_LIBCUDACXX_HIDE_FROM_ABI)\b", row.get("source", ""))
    )
    # A wrapper can intentionally share its final name with a global platform
    # API (cuda::sincos calls ::sincos). A proven global reference wins over
    # the same-name local declaration.
    external_global_names = {
        row["name_hint"].split("::")[-1]
        for row in candidates
        if row.get("must_be_api")
    }
    return names - external_global_names


def _validate_extraction(
    obj: dict,
    candidates: list[dict] | set[str],
    shard: _SourceShard,
    locally_declared_names: set[str] | None = None,
) -> dict:
    if isinstance(candidates, set):
        candidate_meta = {candidate_id: {"candidate_id": candidate_id, "must_be_api": False} for candidate_id in candidates}
    else:
        candidate_meta = {row["candidate_id"]: row for row in candidates}
    candidate_ids = set(candidate_meta)
    apis = obj.get("apis")
    coverage = obj.get("coverage")
    if not isinstance(apis, list) or not isinstance(coverage, list):
        raise ValueError("apis 和 coverage 必须是数组")
    local_ids: set[str] = set()
    for index, api in enumerate(apis):
        if not isinstance(api, dict):
            raise ValueError(f"apis[{index}] 必须是对象")
        required = {"api_id", "name", "kind", "origin", "signature", "source_line_start", "source_line_end", "device_support", "visibility", "summary", "evidence", "candidate_ids"}
        missing = required - set(api)
        if missing:
            raise ValueError(f"apis[{index}] 缺字段: {sorted(missing)}")
        api_id = str(api["api_id"])
        if not api_id or api_id in local_ids:
            raise ValueError(f"重复/空 api_id: {api_id}")
        local_ids.add(api_id)
        api["api_id"] = api_id
        api["name"] = str(api["name"]).strip()
        api["unqualified_name"] = str(api.get("unqualified_name") or api["name"].split("::")[-1]).strip()
        if api["kind"] not in VALID_KINDS or api["device_support"] not in VALID_DEVICE_SUPPORT or api["visibility"] not in VALID_VISIBILITY:
            raise ValueError(f"apis[{index}] 枚举值非法")
        if api["origin"] not in VALID_API_ORIGINS:
            raise ValueError(f"apis[{index}].origin 非法")
        if api["origin"] == "referenced":
            api["name"] = api["name"].removeprefix("::")
            api["unqualified_name"] = api["name"].split("::")[-1]
        exclusion_reason = _api_exclusion_reason(api, locally_declared_names)
        if exclusion_reason:
            raise ValueError(
                f"apis[{index}] 不属于映射范围（{exclusion_reason}）: {api['name']}；"
                "请在 coverage 中标为 non_api"
            )
        if api["visibility"] != "public":
            raise ValueError(f"apis[{index}] 不是公开 API；内部/实现声明只能在 coverage 中标为 non_api")
        start, end = int(api["source_line_start"]), int(api["source_line_end"])
        if start > end or start < shard.start_line or end > shard.end_line:
            raise ValueError(f"apis[{index}] 行号不属于 shard: {start}-{end}")
        api["source_line_start"], api["source_line_end"] = start, end
        if not isinstance(api["candidate_ids"], list) or not set(api["candidate_ids"]).issubset(candidate_ids):
            raise ValueError(f"apis[{index}].candidate_ids 非法")
    covered: list[str] = []
    coverage_by_id: dict[str, dict] = {}
    for row in coverage:
        if not isinstance(row, dict) or row.get("candidate_id") not in candidate_ids:
            raise ValueError("coverage 含未知 candidate_id")
        if row.get("disposition") not in {"api", "non_api", "duplicate", "conditional"}:
            raise ValueError("coverage disposition 非法")
        if not isinstance(row.get("api_ids"), list) or not set(map(str, row["api_ids"])).issubset(local_ids):
            raise ValueError("coverage api_ids 非法")
        row["api_ids"] = [str(value) for value in row["api_ids"]]
        if row["disposition"] == "non_api" and row["api_ids"]:
            raise ValueError("coverage 标为 non_api 时 api_ids 必须为空")
        if row["disposition"] == "api" and not row["api_ids"]:
            raise ValueError("coverage 标为 api 时必须关联 api_id")
        covered.append(row["candidate_id"])
        coverage_by_id[row["candidate_id"]] = row
    if len(covered) != len(set(covered)) or set(covered) != candidate_ids:
        missing = sorted(candidate_ids - set(covered))
        duplicate = sorted(k for k, count in Counter(covered).items() if count > 1)
        raise ValueError(f"coverage 不完整: missing={missing[:20]}, duplicate={duplicate[:20]}")
    for api in apis:
        for candidate_id in api["candidate_ids"]:
            coverage_row = coverage_by_id[candidate_id]
            if coverage_row["disposition"] == "non_api" or api["api_id"] not in coverage_row["api_ids"]:
                raise ValueError(f"API {api['api_id']} 与 coverage {candidate_id} 的分类矛盾")
    for candidate_id, meta in candidate_meta.items():
        if not meta.get("must_be_api"):
            continue
        row = coverage_by_id[candidate_id]
        if row["disposition"] not in {"api", "duplicate", "conditional"} or not row["api_ids"]:
            raise ValueError(f"外部公开 CUDA API 引用 {meta.get('name_hint', candidate_id)} 必须进入 API 结果")
    return {"apis": apis, "coverage": coverage, "chunk_notes": str(obj.get("chunk_notes", ""))}


def _api_key(api: dict) -> tuple:
    return ("referenced", str(api.get("name", "")).strip())


def _deduplicate_apis(apis: list[dict]) -> list[dict]:
    unique: dict[tuple, dict] = {}
    for api in sorted(apis, key=lambda value: (int(value.get("source_line_start", 0)), str(value.get("name", "")), str(value.get("signature", "")))):
        key = _api_key(api)
        if key not in unique:
            unique[key] = dict(api)
        else:
            old = unique[key]
            old["candidate_ids"] = sorted(set(old.get("candidate_ids", [])) | set(api.get("candidate_ids", [])))
            old["source_line_occurrences"] = sorted(set(old.get("source_line_occurrences", [old["source_line_start"]])) | {api["source_line_start"]})
    out = list(unique.values())
    for index, api in enumerate(out, 1):
        api.setdefault("source_line_occurrences", [api["source_line_start"]])
        api["source_api_id"] = f"API{index:06d}"
        api.pop("api_id", None)
    return out


def _validate_mappings(obj: dict, apis: list[dict], docs: _DocIndex, allowed_by_api: dict[str, set[str]]) -> dict:
    mappings = obj.get("mappings")
    if not isinstance(mappings, list):
        raise ValueError("mappings 必须是数组")
    expected = {api["source_api_id"] for api in apis}
    seen: set[str] = set()
    for index, mapping in enumerate(mappings):
        if not isinstance(mapping, dict):
            raise ValueError(f"mappings[{index}] 必须是对象")
        required = {"source_api_id", "accl_apis", "match_status", "doc_paths", "doc_evidence", "mapping_notes", "function_summary"}
        missing = required - set(mapping)
        if missing:
            raise ValueError(f"mappings[{index}] 缺字段: {sorted(missing)}")
        api_id = str(mapping["source_api_id"])
        if api_id not in expected or api_id in seen:
            raise ValueError(f"未知/重复 source_api_id: {api_id}")
        seen.add(api_id)
        if mapping["match_status"] not in VALID_MATCH:
            raise ValueError(f"非法 match_status: {mapping['match_status']}")
        for key in ("accl_apis", "doc_paths", "doc_evidence"):
            if not isinstance(mapping[key], list):
                raise ValueError(f"{key} 必须是数组")
            mapping[key] = [str(value).strip() for value in mapping[key] if str(value).strip()]
        if mapping["match_status"] == "no_match":
            if mapping["accl_apis"] or mapping["doc_paths"] or mapping["doc_evidence"]:
                raise ValueError("no_match 不得携带 API、文档或证据")
        else:
            if not mapping["accl_apis"] or not mapping["doc_paths"]:
                raise ValueError("有匹配时 accl_apis/doc_paths 不得为空")
            if not set(mapping["doc_paths"]).issubset(allowed_by_api.get(api_id, set())):
                raise ValueError("引用了未作为该 API 候选提供给模型的文档")
            cited_text = "\n".join(docs.by_path[path].text for path in mapping["doc_paths"])
            for accl_api in mapping["accl_apis"]:
                plain = accl_api.split("(", 1)[0].split("<", 1)[0].split("::")[-1].strip()
                if plain and plain not in cited_text:
                    raise ValueError(f"文档中未出现映射 API: {accl_api}")
    if seen != expected:
        raise ValueError(f"mappings 不完整: missing={sorted(expected - seen)}")
    return {"mappings": mappings}


def _md_escape(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", "<br>")


def _render_markdown(summary: dict) -> str:
    lines = [
        "| CCCL 侧 API | 来源头文件 | 晟腾侧 API | 对应文档 | 匹配 | 功能简介 |",
        "|---|---|---|---|---|---|",
    ]
    all_apis: list[tuple[str, dict]] = []
    for result in summary["results"]:
        if result.get("status") == "completed":
            all_apis.extend(
                (result["source_file"], api)
                for api in result.get("apis", [])
                if _is_reportable_api(api)
            )
    all_apis.sort(key=lambda item: (item[0], int(item[1].get("source_line_start", 0)), item[1].get("name", ""), item[1].get("signature", "")))
    for source_file, api in all_apis:
        source_label = f"`{source_file}`"
        accl = "<br>".join(f"`{_md_escape(name)}`" for name in api.get("accl_apis", [])) or "—"
        docs = []
        for path in api.get("doc_paths", []):
            docs.append(f"[{_md_escape(Path(path).stem)}](../../docs/SIMT-API/{path})")
        summary_text = api.get("function_summary") or api.get("summary") or ""
        lines.append(
            f"| `{_md_escape(api.get('name'))}` | {source_label} | {accl} | {'<br>'.join(docs) or '—'} | `{api.get('match_status', 'unknown')}` | {_md_escape(summary_text)} |"
        )
    if not all_apis:
        lines.append("| — | — | — | — | — | 尚无已分析 API |")
    return "\n".join(lines) + "\n"
