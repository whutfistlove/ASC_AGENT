"""路径与命名映射。

相对 v2 的改进：
1. 去掉 `if name == "os.h"` 这类写死的特判，module_hint 完全由路径推导。
2. 增加 segment_substitutions（如 __cccl -> __accl）。这正是 v2 缺失的一环：
   v2 只做前缀替换，导致 os.h 的 header guard 算出来是 ..._CCCL_OS_H_，
   而真实示例对里的正确 guard 是 ..._ACCL_OS_H_，两者对不上。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional


def normalize_path_str(path: str) -> str:
    return str(path).replace("\\", "/").strip()


def _relative_after_prefix(input_path: Path, source_repo_prefix: str) -> Optional[str]:
    path_str = normalize_path_str(str(input_path))
    prefix = normalize_path_str(source_repo_prefix).rstrip("/") + "/"
    if prefix in path_str:
        return path_str.split(prefix, 1)[1]
    return None


def apply_segment_substitutions(rel: str, substitutions: Optional[list[dict]]) -> str:
    """对相对路径里的每一段做整段精确替换。"""
    if not substitutions:
        return rel
    table = {s["from"]: s["to"] for s in substitutions}
    parts = normalize_path_str(rel).split("/")
    return "/".join(table.get(p, p) for p in parts)


def infer_module_hint(
    input_path: Path,
    source_repo_prefix: str,
    fallback: str = "generic",
) -> str:
    """
    从路径推导模块提示，例如：
        libcudacxx/include/cuda/std/__algorithm/max.h -> __algorithm
        libcudacxx/include/cuda/std/__cccl/os.h        -> __cccl

    规则（无文件名特判）：
        - 命中源前缀且相对路径含子目录 -> 取第一段目录名
        - 命中源前缀但直接是文件       -> 取文件名 stem
        - 未命中源前缀                 -> 取父目录名，再退到 fallback
    """
    rel = _relative_after_prefix(input_path, source_repo_prefix)
    if rel is not None:
        parts = [p for p in rel.split("/") if p]
        if len(parts) >= 2:
            return parts[0]
        if parts:
            return Path(parts[0]).stem
    parent = Path(input_path).parent.name
    return parent or fallback


def map_target_relpath(
    input_path: Path,
    source_repo_prefix: str,
    target_repo_prefix: str,
    segment_substitutions: Optional[list[dict]] = None,
) -> str:
    """
    libcudacxx/include/cuda/std/<...>
      -> libascendcxx/include/ascend/std/<... 经过段替换 ...>
    """
    rel = _relative_after_prefix(input_path, source_repo_prefix)
    if rel is None:
        raise ValueError(
            f"输入文件不在允许的源前缀下：{source_repo_prefix}\n当前输入：{input_path}"
        )

    rel = apply_segment_substitutions(rel, segment_substitutions)
    tgt_prefix = normalize_path_str(target_repo_prefix).rstrip("/") + "/"
    return tgt_prefix + rel


def expected_guard_from_relpath(target_relpath: str) -> str:
    rel = normalize_path_str(target_relpath).strip("/")
    rel = rel.replace("/", "_").replace(".", "_").replace("-", "_")
    return rel.upper() + "_"
