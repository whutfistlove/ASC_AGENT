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


@dataclass(frozen=True)
class HeaderInventoryEntry:
    relative_path: str
    module: str
    filename: str
    shape: str
    includes: list[str]

    def to_dict(self) -> dict:
        return {
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
    """Return sorted unique `cuda/std/...` includes from C/C++ preprocessor lines."""
    return sorted(set(_CUDA_STD_INCLUDE_RE.findall(text)))


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
    return HeaderInventoryEntry(
        relative_path=relative_path,
        module=infer_header_module(relative_path),
        filename=path.name,
        shape=classify_header_shape(relative_path),
        includes=parse_cuda_std_includes(text),
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
