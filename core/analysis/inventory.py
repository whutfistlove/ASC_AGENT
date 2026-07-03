"""Deterministic CCCL header inventory for real upstream scans."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from fnmatch import fnmatch
from functools import lru_cache
from pathlib import Path
from typing import Mapping, Sequence

from core.common.utils import save_text

DEFAULT_CCCL_REPO = Path("repos/cccl")
# 默认扫描标准库层 cuda/std；扩展层（cuda/，非 std）传不同的 include_root_rel 即可。
HEADER_ROOT_REL = Path("libcudacxx/include/cuda/std")
DEFAULT_REPORT_NAME = "cccl_header_inventory.json"

# 头/测试树位于 libcudacxx/include/<namespace>，<namespace> 即 #include 前缀：
#   libcudacxx/include/cuda/std -> 命名空间 cuda/std（标准库层）
#   libcudacxx/include/cuda     -> 命名空间 cuda  （CUDA 扩展层，cuda::）
INCLUDE_ROOT_PREFIX = "libcudacxx/include"
DEFAULT_INCLUDE_NAMESPACE = "cuda/std"


def namespace_for_root(root: str | Path) -> str:
    """从头根（绝对或相对路径）推导 `#include` 命名空间。

    `.../libcudacxx/include/cuda/std` -> `cuda/std`
    `.../libcudacxx/include/cuda`     -> `cuda`
    找不到标记时回退到 `cuda/std`，保证既有 std 流程行为不变。
    """
    text = str(root).replace("\\", "/")
    marker = INCLUDE_ROOT_PREFIX + "/"
    if marker in text:
        return text.split(marker, 1)[1].strip("/") or DEFAULT_INCLUDE_NAMESPACE
    return DEFAULT_INCLUDE_NAMESPACE


def build_include_re(namespace: str = DEFAULT_INCLUDE_NAMESPACE) -> "re.Pattern[str]":
    """按命名空间构造「仓内 include」匹配正则（如 `cuda/std/...` 或 `cuda/...`）。"""
    ns = str(namespace).strip("/")
    return re.compile(rf'^\s*#\s*include\s*[<"]\s*({re.escape(ns)}/[^>"]+)\s*[>"]')


_INCLUDE_LINE_RE = build_include_re()  # 默认 cuda/std
# 任意 include 目标（`<...>` 或 `"..."`），不限命名空间——用于全量依赖列举（含系统头）。
_ANY_INCLUDE_RE = re.compile(r'^\s*#\s*include\s*[<"]\s*([^>"]+?)\s*[>"]')
_PP_DIRECTIVE_RE = re.compile(r"^\s*#\s*(if|ifdef|ifndef|elif|else|endif)\b(.*)$")


@dataclass(frozen=True)
class SymbolDependencyHit:
    """A source-code symbol reference that implies a header dependency."""

    symbol: str
    include: str
    header: str
    kind: str = "symbol"

    def to_dict(self) -> dict:
        return {
            "header": self.header,
            "include": self.include,
            "kind": self.kind,
            "symbol": self.symbol,
        }


@dataclass(frozen=True)
class IncludeScan:
    """对单个头的 `cuda/std/...` include 做预处理感知扫描的结果。

    - ``active``：会被实际编译进来的依赖（含条件块内的，但**排除 `#if 0` 死块**）。
    - ``conditional``：处于非 include-guard 的 `#if/#ifdef/...` 条件块内的依赖子集（可能不总被编进来）。
    - ``dead``：位于 `#if 0` 死块内、不会被编译的依赖（仅诊断用，不计入依赖图）。
    """

    active: list[str]
    conditional: list[str]
    dead: list[str]


def _strip_comments_and_literals(text: str) -> str:
    """Return C++ text with comments/string/char literals replaced by spaces."""
    out: list[str] = []
    i = 0
    n = len(text)
    state = "code"
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if state == "code":
            if ch == "/" and nxt == "/":
                out.extend("  ")
                i += 2
                state = "line_comment"
                continue
            if ch == "/" and nxt == "*":
                out.extend("  ")
                i += 2
                state = "block_comment"
                continue
            if ch == '"':
                out.append(" ")
                i += 1
                state = "string"
                continue
            if ch == "'":
                out.append(" ")
                i += 1
                state = "char"
                continue
            out.append(ch)
            i += 1
            continue
        if state == "line_comment":
            out.append("\n" if ch == "\n" else " ")
            i += 1
            if ch == "\n":
                state = "code"
            continue
        if state == "block_comment":
            if ch == "*" and nxt == "/":
                out.extend("  ")
                i += 2
                state = "code"
            else:
                out.append("\n" if ch == "\n" else " ")
                i += 1
            continue
        if state in {"string", "char"}:
            if ch == "\\" and nxt:
                out.extend("  ")
                i += 2
                continue
            quote = '"' if state == "string" else "'"
            out.append("\n" if ch == "\n" else " ")
            i += 1
            if ch == quote:
                state = "code"
            continue
    return "".join(out)


def _symbol_rule_include(rule: Mapping, namespace: str = DEFAULT_INCLUDE_NAMESPACE) -> str:
    include = str(rule.get("include") or "")
    if include:
        return include
    header = str(rule.get("header") or "").strip("/")
    return f"{namespace.strip('/')}/{header}" if header else ""


def _symbol_rule_header(rule: Mapping, namespace: str = DEFAULT_INCLUDE_NAMESPACE) -> str:
    header = str(rule.get("header") or "").strip("/")
    if header:
        return header
    return include_to_header_relpath(_symbol_rule_include(rule, namespace), namespace) or ""


def _symbol_occurs(searchable: str, symbol: str) -> bool:
    pattern = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(symbol)}(?![A-Za-z0-9_])")
    return pattern.search(searchable) is not None


def _header_stem(header: str) -> str:
    name = Path(header).name
    return name.rsplit(".", 1)[0] if "." in name else name


@lru_cache(maxsize=8)
def _provider_index(known_headers: tuple[str, ...]) -> dict[str, tuple[str, ...]]:
    by_stem: dict[str, list[str]] = {}
    for header in known_headers:
        by_stem.setdefault(_header_stem(header), []).append(header)
    return {stem: tuple(sorted(headers)) for stem, headers in by_stem.items()}


def _resolve_header_stem_provider(
    symbol: str,
    rule: Mapping,
    known_headers: Sequence[str],
    *,
    current_header: str = "",
) -> str | None:
    """Resolve a qualified symbol to a provider using the source-tree header index.

    Exact filename matches win.  If enabled, ``move_if_noexcept``-style names
    fall back to the longest header-stem prefix (``move.h``).  Module priority
    breaks otherwise ambiguous matches; an unresolved tie is deliberately
    ignored instead of inventing an edge.
    """
    header_tuple = tuple(known_headers)
    index = _provider_index(header_tuple)
    # A qualified recursive/overload call inside the same-stem header is local;
    # do not redirect it to another module that happens to share the basename.
    if current_header and _header_stem(current_header) == symbol:
        return None
    overrides = rule.get("provider_overrides") or {}
    override = str(overrides.get(symbol) or "") if isinstance(overrides, Mapping) else ""
    if override and override in header_tuple and override != current_header:
        return override
    provider_modules = {str(x).strip("/") for x in (rule.get("provider_modules") or [])}

    def allowed(header: str) -> bool:
        if not provider_modules:
            return True
        module = header.split("/", 1)[0] if "/" in header else ""
        return module in provider_modules

    patterns = rule.get("header_globs") or ["**/{symbol}.h", "**/{symbol}"]
    patterns = [str(p).format(symbol=symbol) for p in patterns]
    candidates = [
        h for h in index.get(symbol, ())
        if h != current_header and allowed(h) and any(fnmatch(h, pattern) for pattern in patterns)
    ]
    matched_stem = symbol
    if not candidates and rule.get("prefix_fallback", False):
        stems = {
            stem for stem in index
            if len(stem) >= int(rule.get("minimum_prefix_length", 3))
            and symbol.startswith(stem + "_")
            and any(allowed(h) for h in index.get(stem, ()))
        }
        if stems:
            matched_stem = max(stems, key=len)
            candidates = [
                h for h in index.get(matched_stem, ()) if h != current_header and allowed(h)
            ]
    if not candidates:
        return None

    priorities = [str(x).strip("/") for x in (rule.get("module_priority") or [])]

    def rank(header: str) -> tuple[int, int, str]:
        module = header.split("/", 1)[0] if "/" in header else ""
        priority = priorities.index(module) if module in priorities else len(priorities)
        exact = 0 if _header_stem(header) == symbol else 1
        return (exact, priority, header)

    ordered = sorted(candidates, key=rank)
    best = rank(ordered[0])[:2]
    if len(ordered) > 1 and rank(ordered[1])[:2] == best:
        return None
    return ordered[0]


def _generic_dependency_hits(
    searchable: str,
    rule: Mapping,
    known_headers: Sequence[str],
    *,
    namespace: str,
    current_header: str,
) -> list[SymbolDependencyHit]:
    pattern_text = str(rule.get("pattern") or "")
    if not pattern_text:
        return []
    try:
        pattern = re.compile(pattern_text)
    except re.error:
        return []
    resolver = str(rule.get("resolver") or "")
    if resolver != "header_stem":
        return []
    group = str(rule.get("symbol_group") or "symbol")
    out: list[SymbolDependencyHit] = []
    for match in pattern.finditer(searchable):
        try:
            symbol_name = match.group(group)
        except (IndexError, KeyError):
            continue
        header = _resolve_header_stem_provider(
            symbol_name, rule, known_headers, current_header=current_header
        )
        if not header:
            continue
        include_template = str(rule.get("include_template") or "{namespace}/{header}")
        include = include_template.format(
            namespace=namespace.strip("/"), header=header, symbol=symbol_name
        )
        out.append(SymbolDependencyHit(
            symbol=match.group(0),
            include=include,
            header=header,
            kind=str(rule.get("kind") or "qualified-name"),
        ))
    return out


def scan_implicit_dependencies(
    text: str,
    rules: Sequence[Mapping] | None = None,
    *,
    namespace: str = DEFAULT_INCLUDE_NAMESPACE,
    known_headers: Sequence[str] | None = None,
    current_header: str = "",
) -> list[SymbolDependencyHit]:
    """Detect explicit or generalized source-symbol dependencies.

    Concrete v1 rules (``symbol`` + ``header``) remain supported.  Generalized
    rules use a regex capture plus a provider resolver and therefore cover new
    qualified symbols without adding one YAML row per spelling.
    """
    if not rules:
        return []
    searchable = _strip_comments_and_literals(text)
    hits: dict[tuple[str, str], SymbolDependencyHit] = {}
    for rule in rules:
        if rule.get("resolver"):
            for hit in _generic_dependency_hits(
                searchable,
                rule,
                known_headers or (),
                namespace=namespace,
                current_header=current_header,
            ):
                hits[(hit.symbol, hit.header)] = hit
            continue
        symbol = str(rule.get("symbol") or "")
        include = _symbol_rule_include(rule, namespace)
        header = _symbol_rule_header(rule, namespace)
        if not symbol or not include or not header:
            continue
        if not _symbol_occurs(searchable, symbol):
            continue
        kind = str(rule.get("kind") or "symbol")
        hits[(symbol, header)] = SymbolDependencyHit(
            symbol=symbol,
            include=include,
            header=header,
            kind=kind,
        )
    return sorted(hits.values(), key=lambda item: (item.header, item.symbol))


def scan_symbol_dependencies(
    text: str,
    rules: Sequence[Mapping] | None = None,
    *,
    namespace: str = DEFAULT_INCLUDE_NAMESPACE,
    known_headers: Sequence[str] | None = None,
    current_header: str = "",
) -> list[SymbolDependencyHit]:
    """Compatibility alias for the v1 function name."""
    return scan_implicit_dependencies(
        text,
        rules,
        namespace=namespace,
        known_headers=known_headers,
        current_header=current_header,
    )


def _eval_pp_condition(keyword: str, expr: str) -> tuple[bool, bool]:
    """便宜地判断一个预处理条件分支：返回 (branch_truth, known)。

    只解析字面 `0`/`1`（覆盖 `#if 0` 注释惯用法）；其余（含 ifdef/ifndef/宏表达式）一律
    视为「未知 → 当作可能为真」，对依赖图取**过包含**（宁可多迁也不漏真实依赖）。
    """
    if keyword == "if":
        token = expr.strip()
        if token == "0":
            return (False, True)
        if token == "1":
            return (True, True)
    return (True, False)


def scan_cuda_std_includes(text: str, include_re: "re.Pattern[str] | None" = None) -> IncludeScan:
    """预处理感知地扫描仓内 include（默认 `cuda/std/...`），区分 active / conditional / dead。

    `include_re` 缺省用 cuda/std；扩展层传 `build_include_re("cuda")` 即可改匹配命名空间。
    """
    return _scan_includes_with(text, include_re or _INCLUDE_LINE_RE)


def scan_all_includes(text: str) -> IncludeScan:
    """预处理感知地扫描**所有** include（含系统头 `<errno.h>`、跨命名空间头等），不做命名空间过滤。

    与 :func:`scan_cuda_std_includes` 完全相同的 `#if` 栈 / `#if 0` 死分支处理，区别仅在于匹配
    任意 include 目标。返回的 active/conditional/dead 里是**原始 include 目标串**（如 `errno.h`、
    `cuda/std/__chrono/duration.h`），供「列出一个头的全部依赖（库内 + 系统/外部）」使用。
    """
    return _scan_includes_with(text, _ANY_INCLUDE_RE)


def _scan_includes_with(text: str, include_re: "re.Pattern[str]") -> IncludeScan:
    """共享的预处理感知 include 扫描核心；按 `include_re` 捕获组 1 作为依赖串。"""
    frames: list[dict] = []  # 每个 #if 块：{active, taken, is_guard}
    active: list[str] = []
    conditional: list[str] = []
    dead: list[str] = []

    def stack_active() -> bool:
        return all(frame["active"] for frame in frames)

    for line in text.splitlines():
        directive = _PP_DIRECTIVE_RE.match(line)
        if directive:
            keyword, rest = directive.group(1), directive.group(2)
            if keyword in ("if", "ifdef", "ifndef"):
                parent_active = stack_active()
                # 文件最外层的第一个 #ifndef/#ifdef 视为 include guard（不算「条件」）。
                is_guard = not frames and keyword in ("ifdef", "ifndef")
                truth, known = _eval_pp_condition(keyword, rest)
                branch = parent_active and (truth if known else True)
                # taken 只在「确定为真」时置位：未知条件不算 taken，从而 #else 分支也按 active 过包含。
                frames.append({"active": branch, "taken": (known and truth), "is_guard": is_guard})
            elif keyword == "elif" and frames:
                parent_active = all(f["active"] for f in frames[:-1])
                truth, known = _eval_pp_condition("if", rest)
                frame = frames[-1]
                frame["active"] = parent_active and (not frame["taken"]) and (truth if known else True)
                frame["taken"] = frame["taken"] or (known and truth)
                frame["is_guard"] = False
            elif keyword == "else" and frames:
                parent_active = all(f["active"] for f in frames[:-1])
                frame = frames[-1]
                frame["active"] = parent_active and (not frame["taken"])
                frame["taken"] = True
                frame["is_guard"] = False
            elif keyword == "endif" and frames:
                frames.pop()
            continue

        include = include_re.match(line)
        if not include:
            continue
        dep = include.group(1)
        if stack_active():
            active.append(dep)
            if any(not frame["is_guard"] for frame in frames):
                conditional.append(dep)
        else:
            dead.append(dep)

    def _uniq(seq: list[str]) -> list[str]:
        return sorted(set(seq))

    return IncludeScan(active=_uniq(active), conditional=_uniq(conditional), dead=_uniq(dead))


@dataclass(frozen=True)
class HeaderInventoryEntry:
    relative_path: str
    module: str
    filename: str
    shape: str
    includes: list[str]
    conditional_includes: list[str] = None  # type: ignore[assignment]
    symbol_dependencies: list[str] = None  # type: ignore[assignment]
    symbol_dependency_hits: list[SymbolDependencyHit] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.conditional_includes is None:
            object.__setattr__(self, "conditional_includes", [])
        if self.symbol_dependencies is None:
            object.__setattr__(self, "symbol_dependencies", [])
        if self.symbol_dependency_hits is None:
            object.__setattr__(self, "symbol_dependency_hits", [])

    def to_dict(self) -> dict:
        return {
            "conditional_includes": list(self.conditional_includes),
            "filename": self.filename,
            "includes": list(self.includes),
            "module": self.module,
            "relative_path": self.relative_path,
            "shape": self.shape,
            "symbol_dependencies": list(self.symbol_dependencies),
            "symbol_dependency_hits": [hit.to_dict() for hit in self.symbol_dependency_hits],
        }


@dataclass(frozen=True)
class HeaderInventoryReport:
    cccl_repo: str
    header_root: str
    headers: list[HeaderInventoryEntry]

    def summary(self) -> dict:
        by_module: dict[str, int] = {}
        by_shape: dict[str, int] = {}
        for header in self.headers:
            by_module[header.module] = by_module.get(header.module, 0) + 1
            by_shape[header.shape] = by_shape.get(header.shape, 0) + 1
        return {
            "by_module": dict(sorted(by_module.items())),
            "by_shape": dict(sorted(by_shape.items())),
            "header_count": len(self.headers),
        }

    def to_dict(self) -> dict:
        return {
            "cccl_repo": self.cccl_repo,
            "header_root": self.header_root,
            "headers": [h.to_dict() for h in self.headers],
            "summary": self.summary(),
        }


def resolve_cccl_repo(
    explicit: str | Path | None = None,
    *,
    env: Mapping[str, str] | None = None,
) -> Path:
    """Resolve the real CCCL root from an explicit value, CCCL_REPO, or default."""
    variables = os.environ if env is None else env
    raw = explicit or variables.get("CCCL_REPO") or DEFAULT_CCCL_REPO
    return Path(raw).expanduser().resolve()


def parse_cuda_std_includes(text: str, include_re: "re.Pattern[str] | None" = None) -> list[str]:
    """Return sorted unique *active* in-tree includes (drops `#if 0` dead blocks)."""
    return scan_cuda_std_includes(text, include_re).active


def include_to_header_relpath(
    include_path: str, namespace: str = DEFAULT_INCLUDE_NAMESPACE
) -> str | None:
    """Convert `<namespace>/foo` to `foo`; return None for unrelated include strings."""
    prefix = namespace.strip("/") + "/"
    if not include_path.startswith(prefix):
        return None
    return include_path[len(prefix):]


def is_env_file(path: str | Path) -> bool:
    name = Path(path).name
    return name == ".env" or name.startswith(".env.")


def infer_header_module(relative_path: str) -> str:
    parts = [p for p in relative_path.split("/") if p]
    if not parts:
        return "unknown"
    if len(parts) == 1:
        return Path(parts[0]).stem or parts[0]
    return parts[0]


def classify_header_shape(relative_path: str) -> str:
    """Classify headers as public or private based on libcudacxx's `__*` convention."""
    parts = [p for p in relative_path.split("/") if p]
    return "private" if any(p.startswith("__") for p in parts) else "public"


def _header_entry(
    path: Path,
    header_root: Path,
    *,
    include_re: "re.Pattern[str] | None" = None,
    namespace: str = DEFAULT_INCLUDE_NAMESPACE,
    implicit_dependency_rules: Sequence[Mapping] | None = None,
    known_headers: Sequence[str] | None = None,
) -> HeaderInventoryEntry:
    relative_path = path.relative_to(header_root).as_posix()
    text = path.read_text(encoding="utf-8", errors="replace")
    scan = scan_cuda_std_includes(text, include_re)
    symbol_hits = scan_implicit_dependencies(
        text,
        implicit_dependency_rules,
        namespace=namespace,
        known_headers=known_headers,
        current_header=relative_path,
    )
    return HeaderInventoryEntry(
        relative_path=relative_path,
        module=infer_header_module(relative_path),
        filename=path.name,
        shape=classify_header_shape(relative_path),
        includes=scan.active,
        conditional_includes=scan.conditional,
        symbol_dependencies=sorted({hit.include for hit in symbol_hits}),
        symbol_dependency_hits=symbol_hits,
    )


def scan_header_inventory(
    cccl_repo: str | Path | None = None,
    *,
    include_root_rel: str | Path = HEADER_ROOT_REL,
    implicit_dependency_rules: Sequence[Mapping] | None = None,
    symbol_dependency_rules: Sequence[Mapping] | None = None,
) -> HeaderInventoryReport:
    """Scan headers without modifying CCCL.

    ``symbol_dependency_rules`` is the deprecated v1 keyword; generalized
    callers should pass ``implicit_dependency_rules``.
    """
    rules = implicit_dependency_rules
    if rules is None:
        rules = symbol_dependency_rules
    repo = resolve_cccl_repo(cccl_repo)
    header_root = repo / Path(include_root_rel)
    if not header_root.is_dir():
        raise FileNotFoundError(f"CCCL header root not found: {header_root}")

    namespace = namespace_for_root(include_root_rel)
    include_re = build_include_re(namespace)
    paths = sorted(p for p in header_root.rglob("*") if p.is_file() and not is_env_file(p))
    known_headers = tuple(p.relative_to(header_root).as_posix() for p in paths)
    headers = [
        _header_entry(
            p, header_root,
            include_re=include_re, namespace=namespace,
            implicit_dependency_rules=rules,
            known_headers=known_headers,
        )
        for p in paths
    ]
    return HeaderInventoryReport(
        cccl_repo=str(repo),
        header_root=str(header_root),
        headers=headers,
    )


def write_inventory_report(
    report: HeaderInventoryReport,
    output_dir: str | Path,
    *,
    filename: str = DEFAULT_REPORT_NAME,
) -> Path:
    name = Path(filename)
    if name.is_absolute() or len(name.parts) != 1:
        raise ValueError("inventory report filename must be a file name under outputs/")
    path = Path(output_dir) / name
    payload = json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
    save_text(path, payload + "\n")
    return path
