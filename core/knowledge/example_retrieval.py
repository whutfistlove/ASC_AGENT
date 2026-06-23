"""少样本示例检索：从 `examples/` 里按算子相关度挑最贴近的示例对/三元组。

动机：原先 few-shot 永远写死 max/os（头）与 max/swap（测试），迁移一个 numeric 算子也只
能看 os.h。示例库增大后，应当**按相关度检索**最贴近的示例喂给模型，而不是固定那两条。

约束对齐：检索池只来自 `examples/`（与源仓并列为「输入」），不读目标仓——符合
「输入只在源仓/examples、输出只在目标仓/outputs」。检索是纯词法、离线、确定性的
（无外部 embedding 依赖）：按「同名算子 + 名称子串亲和 + 源文本 token 重叠(Jaccard)」打分，
取 top-k。示例只有两条时退化为「全选」，与历史行为一致。
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text or "")}


def _name_from_relpath(relpath: str) -> str:
    return Path(str(relpath)).stem


def _read(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _examples_root_from_dir(examples_dir: Path) -> Path:
    examples_dir = Path(examples_dir)
    for candidate in (examples_dir, *examples_dir.parents):
        if (candidate / "manifest.yaml").is_file():
            return candidate
    if examples_dir.name in {"headers", "tests"}:
        return examples_dir.parent
    return examples_dir


def _load_manifest(examples_dir: Path) -> tuple[Path, dict]:
    """Load examples/manifest.yaml if present; missing/bad manifests fall back to scans."""
    root = _examples_root_from_dir(examples_dir)
    path = root / "manifest.yaml"
    if not path.is_file():
        return root, {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return root, {}
    return root, data if isinstance(data, dict) else {}


def _resolve_manifest_path(root: Path, value: str | None, *, default_subdir: str) -> Path | None:
    if not value:
        return None
    p = Path(str(value))
    if p.is_absolute():
        return p
    text = str(value).replace("\\", "/")
    if text.startswith(("headers/", "tests/")):
        return root / p
    return root / default_subdir / p


def _candidate_name(entry: dict, path: Path, suffix: str) -> str:
    if entry.get("name"):
        return str(entry["name"])
    name = path.name
    return name[: -len(suffix)] if name.endswith(suffix) else path.stem


def _metadata_text(candidate: dict) -> str:
    parts: list[str] = []
    for key in (
        "id",
        "name",
        "module",
        "source_header",
        "target_relpath",
        "shape",
        "description",
        "validation_status",
    ):
        value = candidate.get(key)
        if value:
            parts.append(str(value))
    tags = candidate.get("tags")
    if isinstance(tags, list):
        parts.extend(str(tag) for tag in tags)
    elif tags:
        parts.append(str(tags))
    return " ".join(parts)


def _candidate_text(candidate: dict, *path_keys: str) -> str:
    body = "\n".join(_read(candidate.get(key, "")) for key in path_keys)
    return _metadata_text(candidate) + "\n" + body


def _shape_signature(text: str) -> str:
    """从源/测试文本粗略推断算子形态，用于「同形态」few-shot 检索加权。

    确定性、容错的粗分类（宁可判错也不抛错）：
      * ``multi_return``：返回 pair/tuple（如 minmax）——多输出形态；
      * ``inplace_void``：返回 void 的函数模板（如 swap/iter_swap）——原地、无返回值；
      * ``value``：其余（二元/一元返回值，如 max/clamp）。
    形态匹配给一个**温和**的加权（介于名称亲和与同名之间），只在相近候选间起决胜作用。
    """
    t = text or ""
    if re.search(r"\b(pair|tuple)\s*<", t):
        return "multi_return"
    if re.search(r"\bvoid\s+[A-Za-z_]\w*\s*\(", t):
        return "inplace_void"
    return "value"


def _score(
    query_name: str,
    query_tokens: set[str],
    cand_name: str,
    cand_tokens: set[str],
    query_shape: str = "",
    cand_shape: str = "",
) -> float:
    """相关度打分：同名最高，名称子串亲和次之，叠加源文本 token Jaccard 重叠 + 同形态加权。"""
    score = 0.0
    if cand_name and query_name:
        if cand_name == query_name:
            score += 1000.0           # 同名算子（如迁 swap 命中 swap 示例）最相关
        elif cand_name in query_name or query_name in cand_name:
            score += 30.0             # minmax ~ min / max 这类名称亲和
    if query_shape and cand_shape and query_shape == cand_shape:
        score += 25.0                 # 同形态（如都为原地 void / 都为多返回）更可迁移借鉴
    if query_tokens and cand_tokens:
        inter = len(query_tokens & cand_tokens)
        union = len(query_tokens | cand_tokens)
        if union:
            score += 100.0 * inter / union
    return score


def _rank(candidates: list[dict], *, query_name: str, query_text: str,
          text_of, k: int) -> list[dict]:
    """按相关度排序取 top-k。稳定排序：同分保持原始顺序（可复现）。"""
    qtokens = _tokens(query_text)
    qshape = _shape_signature(query_text)
    scored = []
    for idx, c in enumerate(candidates):
        cand_text = text_of(c)
        s = _score(
            query_name, qtokens, c.get("name", ""), _tokens(cand_text),
            query_shape=qshape, cand_shape=_shape_signature(cand_text),
        )
        scored.append((s, -idx, c))
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [c for _, _, c in scored[: max(1, k)]]


# --------------------------------------------------------------------------- #
# 池发现（只扫 examples/ 目录）
# --------------------------------------------------------------------------- #
def discover_header_pairs(examples_dir: Path) -> list[dict]:
    """examples header pairs.

    Prefer examples/manifest.yaml so identities are stable even when two examples
    share the same basename; fall back to filesystem discovery for older fixtures.
    """
    out: list[dict] = []
    examples_dir = Path(examples_dir)
    if not examples_dir.is_dir():
        return out
    root, manifest = _load_manifest(examples_dir)
    for entry in manifest.get("headers") or []:
        if not isinstance(entry, dict):
            continue
        cccl = _resolve_manifest_path(root, entry.get("cccl"), default_subdir="headers")
        accl = _resolve_manifest_path(root, entry.get("accl"), default_subdir="headers")
        if cccl and accl and cccl.exists() and accl.exists():
            item = dict(entry)
            item.update({
                "name": _candidate_name(entry, cccl, ".cccl.h"),
                "cccl": str(cccl),
                "accl": str(accl),
            })
            out.append(item)
    if out:
        return out
    for cccl in sorted(examples_dir.rglob("*.cccl.h")):
        name = cccl.name[: -len(".cccl.h")]
        accl = cccl.with_name(f"{name}.accl.h")
        if accl.exists():
            out.append({"name": name, "cccl": str(cccl), "accl": str(accl)})
    return out


def discover_test_triples(examples_dir: Path) -> list[dict]:
    """examples test triples, with manifest identities preferred over bare names."""
    out: list[dict] = []
    examples_dir = Path(examples_dir)
    if not examples_dir.is_dir():
        return out
    root, manifest = _load_manifest(examples_dir)
    for entry in manifest.get("tests") or []:
        if not isinstance(entry, dict):
            continue
        cccl = _resolve_manifest_path(root, entry.get("cccl_test"), default_subdir="tests")
        host = _resolve_manifest_path(root, entry.get("accl_host"), default_subdir="tests")
        spec = _resolve_manifest_path(root, entry.get("accl_kernel_spec"), default_subdir="tests")
        if cccl and host and spec and cccl.exists() and host.exists() and spec.exists():
            item = dict(entry)
            item.update({
                "name": _candidate_name(entry, cccl, ".cccl.pass.cpp"),
                "cccl_test": str(cccl),
                "accl_host": str(host),
                "accl_kernel_spec": str(spec),
            })
            out.append(item)
    if out:
        return out
    for cccl in sorted(examples_dir.rglob("*.cccl.pass.cpp")):
        name = cccl.name[: -len(".cccl.pass.cpp")]
        host = cccl.with_name(f"{name}.accl_host.cpp")
        spec = cccl.with_name(f"{name}.accl_kernel_spec.json")
        if host.exists() and spec.exists():
            out.append({
                "name": name,
                "cccl_test": str(cccl), "accl_host": str(host), "accl_kernel_spec": str(spec),
            })
    return out


def _merge_keep_configured(pool: list[dict], configured: list[dict]) -> list[dict]:
    """以 manifest/目录扫描池为主，补齐 configured 里有但扫描漏掉的项。"""
    by_name = {_candidate_identity(c): c for c in pool}
    for c in configured:
        by_name.setdefault(_candidate_identity(c), c)
    return list(by_name.values())


def _candidate_identity(candidate: dict) -> str:
    path_keys = ("cccl", "accl", "cccl_test", "accl_host", "accl_kernel_spec")
    paths = tuple(str(candidate.get(key, "")) for key in path_keys if candidate.get(key))
    if paths:
        return "paths:" + "|".join(paths)
    for key in ("id", "source_header", "target_relpath"):
        if candidate.get(key):
            return f"{key}:{candidate[key]}"
    return "name:" + str(candidate.get("name", ""))


# --------------------------------------------------------------------------- #
# 对外：选头文件示例 / 选测试示例
# --------------------------------------------------------------------------- #
def _drop_self(pool: list[dict], name: str, exclude_self: bool,
               *, target_relpath: str = "") -> list[dict]:
    """exclude_self 时把与当前算子同名的候选剔除——避免「迁 X 却把 X 的答案当示例」的泄漏。"""
    if not exclude_self or not name:
        return pool
    target_relpath = target_relpath.strip("/")
    kept: list[dict] = []
    for candidate in pool:
        cand_target = str(candidate.get("target_relpath", "")).strip("/")
        if cand_target and target_relpath:
            if cand_target == target_relpath:
                continue
        elif candidate.get("name") == name:
            continue
        kept.append(candidate)
    return kept


def select_header_examples(config, *, target_relpath: str, source_text: str,
                           k: int = 2, enabled: bool = True,
                           exclude_self: bool = False) -> list[tuple[str, str]]:
    """返回有序的 (cccl_path, accl_path) 列表（按与当前算子的相关度，最相关在前）。"""
    configured = [
        {"name": _stem_of_cccl_header(ex["cccl"]), "cccl": str(ex["cccl"]), "accl": str(ex["accl"])}
        for ex in config.example_paths().values()
        if ex.get("cccl") and ex.get("accl")
    ]
    query_name = _name_from_relpath(target_relpath)
    if not enabled:
        fallback = _drop_self(configured, query_name, exclude_self, target_relpath=target_relpath)
        return [(c["cccl"], c["accl"]) for c in fallback[: max(1, k)]]
    if not configured:
        return []

    examples_dir = Path(configured[0]["cccl"]).parent
    pool = _drop_self(
        _merge_keep_configured(discover_header_pairs(examples_dir), configured),
        query_name, exclude_self, target_relpath=target_relpath,
    )
    if not pool:
        return []
    ranked = _rank(
        pool, query_name=query_name, query_text=source_text,
        text_of=lambda c: _candidate_text(c, "cccl", "accl"), k=k,
    )
    return [(c["cccl"], c["accl"]) for c in ranked]


def select_test_examples(config, *, algo_name: str, cccl_test_text: str,
                         k: int = 2, enabled: bool = True,
                         exclude_self: bool = False) -> list[dict]:
    """返回有序的测试示例三元组列表（dict: cccl_test/accl_host/accl_kernel_spec）。"""
    configured = [
        {"name": _stem_of_cccl_test(ex["cccl_test"]),
         "cccl_test": str(ex["cccl_test"]), "accl_host": str(ex["accl_host"]),
         "accl_kernel_spec": str(ex["accl_kernel_spec"])}
        for ex in config.test_example_paths().values()
        if ex.get("cccl_test") and ex.get("accl_host") and ex.get("accl_kernel_spec")
    ]
    if not enabled:
        return _drop_self(configured, str(algo_name), exclude_self)[: max(1, k)]
    if not configured:
        return []

    examples_dir = Path(configured[0]["cccl_test"]).parent
    pool = _drop_self(
        _merge_keep_configured(discover_test_triples(examples_dir), configured),
        str(algo_name), exclude_self,
    )
    return _rank(
        pool, query_name=str(algo_name), query_text=cccl_test_text,
        text_of=lambda c: _candidate_text(c, "cccl_test", "accl_host", "accl_kernel_spec"), k=k,
    )


def _stem_of_cccl_header(path: str) -> str:
    name = Path(path).name
    return name[: -len(".cccl.h")] if name.endswith(".cccl.h") else Path(path).stem


def _stem_of_cccl_test(path: str) -> str:
    name = Path(path).name
    return name[: -len(".cccl.pass.cpp")] if name.endswith(".cccl.pass.cpp") else Path(path).stem
