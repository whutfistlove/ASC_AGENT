"""Deterministic CCCL header inventory for real upstream scans."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from core.utils import save_text

DEFAULT_CCCL_REPO = Path("/home/zhenyu/projects/cccl")
HEADER_ROOT_REL = Path("libcudacxx/include/cuda/std")
DEFAULT_REPORT_NAME = "cccl_header_inventory.json"

_CUDA_STD_INCLUDE_RE = re.compile(
    r'^\s*#\s*include\s*[<"]\s*(cuda/std/[^>"]+)\s*[>"]',
    re.MULTILINE,
)
_INCLUDE_LINE_RE = re.compile(r'^\s*#\s*include\s*[<"]\s*(cuda/std/[^>"]+)\s*[>"]')
_PP_DIRECTIVE_RE = re.compile(r"^\s*#\s*(if|ifdef|ifndef|elif|else|endif)\b(.*)$")


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


def scan_cuda_std_includes(text: str) -> IncludeScan:
    """预处理感知地扫描 `cuda/std/...` include，区分 active / conditional / dead。"""
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

        include = _INCLUDE_LINE_RE.match(line)
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

    def __post_init__(self):
        if self.conditional_includes is None:
            object.__setattr__(self, "conditional_includes", [])

    def to_dict(self) -> dict:
        return {
            "conditional_includes": list(self.conditional_includes),
            "filename": self.filename,
            "includes": list(self.includes),
            "module": self.module,
            "relative_path": self.relative_path,
            "shape": self.shape,
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


def parse_cuda_std_includes(text: str) -> list[str]:
    """Return sorted unique *active* `cuda/std/...` includes (drops `#if 0` dead blocks)."""
    return scan_cuda_std_includes(text).active


def include_to_header_relpath(include_path: str) -> str | None:
    """Convert `cuda/std/foo` to `foo`; return None for non-CCCL include strings."""
    prefix = "cuda/std/"
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


def _header_entry(path: Path, header_root: Path) -> HeaderInventoryEntry:
    relative_path = path.relative_to(header_root).as_posix()
    text = path.read_text(encoding="utf-8", errors="replace")
    scan = scan_cuda_std_includes(text)
    return HeaderInventoryEntry(
        relative_path=relative_path,
        module=infer_header_module(relative_path),
        filename=path.name,
        shape=classify_header_shape(relative_path),
        includes=scan.active,
        conditional_includes=scan.conditional,
    )


def scan_header_inventory(
    cccl_repo: str | Path | None = None,
    *,
    include_root_rel: str | Path = HEADER_ROOT_REL,
) -> HeaderInventoryReport:
    """Scan `libcudacxx/include/cuda/std` without modifying the CCCL repository."""
    repo = resolve_cccl_repo(cccl_repo)
    header_root = repo / Path(include_root_rel)
    if not header_root.is_dir():
        raise FileNotFoundError(f"CCCL header root not found: {header_root}")

    paths = sorted(p for p in header_root.rglob("*") if p.is_file() and not is_env_file(p))
    headers = [_header_entry(p, header_root) for p in paths]
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
