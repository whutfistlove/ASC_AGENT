"""路径与命名映射。

相对 v2 的改进：
1. 去掉 `if name == "os.h"` 这类写死的特判，module_hint 完全由路径推导。
2. 增加 segment_substitutions（如 __cccl -> __asc）。这正是 v2 缺失的一环：
   v2 只做前缀替换，导致 os.h 的 header guard 算出来是 ..._CCCL_OS_H_，
   而真实示例对里的正确 guard 是 ..._ASC_OS_H_，两者对不上。
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
      -> asc-stl/include/asc/std/<... 经过段替换 ...>
    """
    rel = _relative_after_prefix(input_path, source_repo_prefix)
    if rel is None:
        raise ValueError(
            f"输入文件不在允许的源前缀下：{source_repo_prefix}\n当前输入：{input_path}"
        )

    rel = apply_segment_substitutions(rel, segment_substitutions)
    tgt_prefix = normalize_path_str(target_repo_prefix).rstrip("/") + "/"
    return tgt_prefix + rel


def source_header_relpath(input_path: Path, source_repo_prefix: str) -> Optional[str]:
    """从 CCCL 输入路径推导其相对 `source_repo_prefix` 的 header 键（如 `__algorithm/min.h`）。

    与 `inventory.HeaderInventoryEntry.relative_path` / `migration_status` 的 header 键同口径，
    便于把「测试通过」结论按同一个键回写进 `core.migration_state`。不在源前缀下返回 None。
    """
    return _relative_after_prefix(input_path, source_repo_prefix)


def map_cccl_test_path(
    input_path: Path,
    source_repo_prefix: str,
    cccl_test_prefix: str,
    suffix: str = ".pass.cpp",
) -> str:
    """从 CCCL 算子头文件路径推导其 CCCL 侧测试源路径（平行 test 树）。

        <root>/libcudacxx/include/cuda/std/__algorithm/min.h
          -> <root>/libcudacxx/test/libcudacxx/std/__algorithm/min.pass.cpp

    保持算子的子路径段不变（如 __algorithm/min），仅把 include 前缀换成 test 前缀、
    把头文件后缀换成测试后缀。返回绝对路径字符串；调用方负责判断是否存在。
    """
    path_str = normalize_path_str(str(input_path))
    prefix = normalize_path_str(source_repo_prefix).rstrip("/") + "/"
    if prefix not in path_str:
        raise ValueError(
            f"输入文件不在允许的源前缀下：{source_repo_prefix}\n当前输入：{input_path}"
        )
    root, rel = path_str.split(prefix, 1)  # root 以 '/' 结尾
    stem = normalize_path_str(str(Path(rel).with_suffix("")))  # __algorithm/min
    test_prefix = normalize_path_str(cccl_test_prefix).strip("/")
    return root + test_prefix + "/" + stem + suffix


def expected_guard_from_relpath(target_relpath: str) -> str:
    rel = normalize_path_str(target_relpath).strip("/")
    rel = rel.replace("/", "_").replace(".", "_").replace("-", "_")
    return rel.upper() + "_"
