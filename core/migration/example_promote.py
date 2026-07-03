"""把「已验证的迁移产物」晋升为 examples/ 里的金标准 few-shot 示例。

这是一次**人工 curation**（不是 agent 运行时读目标仓）：从 `repos/accl` 里挑**已通过测试**
的算子，连同它的 CCCL 源头、ACCL 头、CCCL 测试、ACCL host 测试、kernel_spec 一并复制进
`examples/`，让检索式 few-shot（`core/example_retrieval.py`）有更丰富、更普遍的池子可挑。

与 I/O 边界的关系：运行时边界不变——agent 迁移时仍只读 `cccl + examples`、只写 `accl + outputs`。
「晋升」是一条独立的、人触发的 curation 步骤（把已验证的*输出*沉淀为可复用的*输入*），
不是 agent 在跑迁移时去读目标仓。

质量门禁：晋升前校验 ACCL 头含 guard、host 测试经 `validate_host_test_code`、kernel_spec 经
`validate_kernel_spec`——避免把劣质/占位产物灌进示例库，污染后续所有迁移。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import yaml

from core.common.config import Config
from core.common.utils import save_text
from core.testing.test_migrator import validate_host_test_code, validate_kernel_spec

# host/kernel 测试在目标仓里的固定结构（与 core/operator_test.py 一致）。
_HOST_SUBDIR = ("asc-stl", "test", "asc-stl", "asc", "host")
_KERNEL_SUBDIR = ("asc-stl", "test", "asc-stl", "asc", "kernel")


@dataclass
class OperatorArtifacts:
    op_name: str
    module: str = ""
    cccl_header: Path | None = None
    accl_header: Path | None = None
    cccl_test: Path | None = None
    host_test: Path | None = None
    kernel_spec: Path | None = None

    def has_header_pair(self) -> bool:
        return bool(self.cccl_header and self.cccl_header.is_file()
                    and self.accl_header and self.accl_header.is_file())

    def has_test_set(self) -> bool:
        return bool(
            self.cccl_test and self.cccl_test.is_file()
            and self.host_test and self.host_test.is_file()
            and self.kernel_spec and self.kernel_spec.is_file()
        )


def resolve_artifacts(config: Config, op_name: str, module: str | None = None) -> OperatorArtifacts:
    """按算子名定位它在源仓/目标仓里的全部产物。module 省略时按头文件名在目标仓搜索。"""
    accl_root = Path(config.accl_repo)
    cccl_root = Path(config.cccl_repo)
    target_prefix = config.target_repo_prefix
    source_prefix = config.source_repo_prefix

    accl_header: Path | None = None
    if module:
        cand = accl_root / target_prefix / module / f"{op_name}.h"
        accl_header = cand if cand.is_file() else None
    else:
        matches = sorted((accl_root / target_prefix).glob(f"**/{op_name}.h"))
        accl_header = matches[0] if matches else None
        module = accl_header.parent.name if accl_header else ""

    cccl_header = (cccl_root / source_prefix / module / f"{op_name}.h") if module else None
    cccl_test = (
        cccl_root / config.cccl_test_prefix / module / f"{op_name}{config.cccl_test_suffix}"
        if module else None
    )
    host_test = accl_root.joinpath(*_HOST_SUBDIR) / f"{op_name}_tests.cpp"
    kernel_spec = accl_root.joinpath(*_KERNEL_SUBDIR) / f"{op_name}_example" / "kernel_spec.json"
    return OperatorArtifacts(op_name, module, cccl_header, accl_header, cccl_test, host_test, kernel_spec)


def discover_promotable(config: Config) -> list[str]:
    """列出「目标仓已有 ACCL 头、且源仓有对应 CCCL 头」的算子名（可晋升候选）。"""
    accl_root = Path(config.accl_repo)
    target_prefix = config.target_repo_prefix
    out: list[str] = []
    base = accl_root / target_prefix
    if not base.is_dir():
        return out
    for header in sorted(base.glob("**/*.h")):
        name = header.stem
        art = resolve_artifacts(config, name, module=header.parent.name)
        if art.has_header_pair():
            out.append(name)
    return out


def _examples_dirs(config: Config) -> tuple[Path, Path]:
    return (config.project_root / "examples" / "headers",
            config.project_root / "examples" / "tests")


def _examples_root(config: Config) -> Path:
    return config.project_root / "examples"


def _copy_text(src: Path, dst: Path, overwrite: bool) -> bool:
    """复制文本（统一 LF）。dst 已存在且未 overwrite 时跳过，返回是否写入。"""
    if dst.exists() and not overwrite:
        return False
    save_text(dst, Path(src).read_text(encoding="utf-8"))
    return True


def _shape_signature(text: str) -> str:
    if "pair<" in text or "tuple<" in text:
        return "multi_return"
    if " void " in text or text.lstrip().startswith("void "):
        return "inplace_void"
    return "value"


def _load_manifest(path: Path) -> dict:
    if not path.is_file():
        return {"schema_version": 1, "headers": [], "tests": []}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("schema_version", 1)
    data.setdefault("headers", [])
    data.setdefault("tests", [])
    return data


def _upsert_by_id(items: list, item: dict) -> None:
    for idx, existing in enumerate(items):
        if isinstance(existing, dict) and existing.get("id") == item.get("id"):
            items[idx] = item
            return
    items.append(item)


def _save_manifest_if_changed(path: Path, data: dict) -> bool:
    text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    if not text.endswith("\n"):
        text += "\n"
    old = path.read_text(encoding="utf-8") if path.is_file() else ""
    if old == text:
        return False
    save_text(path, text)
    return True


def _update_manifest(config: Config, art: OperatorArtifacts, *, promote_test: bool) -> bool:
    root = _examples_root(config)
    manifest_path = root / "manifest.yaml"
    data = _load_manifest(manifest_path)
    module = art.module or "unknown"
    entry_id = f"{module}.{art.op_name}"
    source_header = f"{module}/{art.op_name}.h" if art.module else f"{art.op_name}.h"
    target_relpath = f"{config.target_repo_prefix}/{source_header}"
    shape = ""
    if art.cccl_header and art.cccl_header.is_file():
        shape = _shape_signature(art.cccl_header.read_text(encoding="utf-8", errors="replace"))

    _upsert_by_id(data["headers"], {
        "id": entry_id,
        "name": art.op_name,
        "module": module,
        "source_header": source_header,
        "target_relpath": target_relpath,
        "cccl": f"headers/{art.op_name}.cccl.h",
        "accl": f"headers/{art.op_name}.accl.h",
        "shape": shape or "value",
        "tags": [module, art.op_name],
        "validation_status": "curated",
    })
    if promote_test:
        _upsert_by_id(data["tests"], {
            "id": entry_id,
            "name": art.op_name,
            "module": module,
            "source_header": source_header,
            "cccl_test": f"tests/{art.op_name}.cccl.pass.cpp",
            "accl_host": f"tests/{art.op_name}.accl_host.cpp",
            "accl_kernel_spec": f"tests/{art.op_name}.accl_kernel_spec.json",
            "shape": shape or "value",
            "tags": [module, art.op_name],
            "validation_status": "curated",
        })
    return _save_manifest_if_changed(manifest_path, data)


def promote_operator(
    config: Config,
    op_name: str,
    *,
    module: str | None = None,
    overwrite: bool = False,
    validate: bool = True,
    include_test: bool = True,
) -> dict:
    """把一个已迁移算子晋升为 examples/ 金标准示例（头对 + 可选测试三元组）。

    返回 {"op", "module", "header_written", "test_written", "skipped": [...]}。
    缺 ACCL/CCCL 头直接报错；测试三件不全则只晋升头对（不报错）。
    """
    art = resolve_artifacts(config, op_name, module)
    if not (art.accl_header and art.accl_header.is_file()):
        raise FileNotFoundError(f"找不到已迁移的 ACCL 头：{op_name}（请先迁移该算子）")
    if not (art.cccl_header and art.cccl_header.is_file()):
        raise FileNotFoundError(f"找不到对应的 CCCL 源头：{op_name}")

    accl_text = art.accl_header.read_text(encoding="utf-8")
    if validate and "#ifndef" not in accl_text:
        raise ValueError(f"ACCL 头疑似无效（缺 include guard）：{art.accl_header}")

    headers_dir, tests_dir = _examples_dirs(config)
    result: dict = {"op": op_name, "module": art.module, "header_written": False,
                    "test_written": False, "manifest_written": False, "skipped": []}

    # 实测验证门禁：若 migration_state 里**有**该算子的记录但状态不是 host/kernel 通过，
    # 拒绝晋升（避免把「编得过但从未真正测过 / 测过没过」的产物当金标准）。无记录则不拦
    # （可能在别的机器上测过），退回静态门禁——保持既有 curation 行为，只增不减严格度。
    if validate and art.module:
        from core.analysis.migration_state import (
            DEFAULT_STATE_FILENAME,
            VALIDATED_STATUSES,
            MigrationStateStore,
        )

        store = MigrationStateStore.load(config.state_output_dir / DEFAULT_STATE_FILENAME)
        entry = store.headers.get(f"{art.module}/{op_name}.h")
        if entry is not None and entry.status not in VALIDATED_STATUSES:
            result["skipped"].append(f"promotion_blocked_state_status:{entry.status}")
            return result

    # 先决定测试是否可晋升（落盘前过质量门禁）：门禁不过则**跳过测试**（不报错），
    # 头仍照常晋升——坏测试不进库，好头照样复用。minmax 的「假绿」host 测试即被此拦下。
    spec = None
    promote_test = False
    if include_test:
        if not art.has_test_set():
            result["skipped"].append("test(产物不全：缺 CCCL 测试 / host 测试 / kernel_spec)")
        else:
            try:
                spec = json.loads(art.kernel_spec.read_text(encoding="utf-8"))
                if validate:
                    validate_host_test_code(art.host_test.read_text(encoding="utf-8"))
                    spec = validate_kernel_spec(spec)
                promote_test = True
            except (ValueError, json.JSONDecodeError) as exc:
                result["skipped"].append(f"test(未过质量门禁：{exc})")

    wrote_c = _copy_text(art.cccl_header, headers_dir / f"{op_name}.cccl.h", overwrite)
    wrote_a = _copy_text(art.accl_header, headers_dir / f"{op_name}.accl.h", overwrite)
    result["header_written"] = wrote_c or wrote_a
    if not result["header_written"]:
        result["skipped"].append("header(已存在，未 overwrite)")

    if promote_test:
        w1 = _copy_text(art.cccl_test, tests_dir / f"{op_name}.cccl.pass.cpp", overwrite)
        w2 = _copy_text(art.host_test, tests_dir / f"{op_name}.accl_host.cpp", overwrite)
        spec_path = tests_dir / f"{op_name}.accl_kernel_spec.json"
        w3 = False
        if overwrite or not spec_path.exists():
            save_text(spec_path, json.dumps(spec, ensure_ascii=False, indent=2))
            w3 = True
        result["test_written"] = w1 or w2 or w3
        if not result["test_written"]:
            result["skipped"].append("test(已存在，未 overwrite)")

    result["manifest_written"] = _update_manifest(config, art, promote_test=promote_test)
    return result
