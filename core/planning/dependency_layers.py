"""整包严格依赖分层（确定性、不调模型、不看迁移状态）。

与 :mod:`core.planning.package_planner` 的区别：那是「迁移活台账」——会丢掉已完成头、按策略
延期、把不可解析的头标 blocked，且每个头只给依赖**数量**。本模块给的是整包的**纯结构视图**：

  * Layer 0 = 库内零依赖头（优先迁移的那一批）；
  * Layer N 只依赖 Layer < N；
  * 每个头列出它的**全部**依赖：库内依赖（决定分层）+ 外部/系统 include（如 ``<errno.h>``、
    ``<pthread.h>``，只列出、不参与分层，因为它们不是迁移目标）；
  * 处于依赖环（强连通分量）里的头同层，并标记 ⟲（需一起迁移）。

复用既有事实，绝不调用模型：
  * 库内依赖边 / 环  -> :mod:`core.analysis.dep_graph`
  * 全量 include（含系统头）-> :func:`core.analysis.inventory.scan_all_includes`
  * SCC 凝聚 + 分层波次 -> :func:`core.planning.package_planner._condensation_waves`
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from core.analysis.dep_graph import HeaderDependencyGraphReport
from core.analysis.inventory import (
    HeaderInventoryReport,
    include_to_header_relpath,
    infer_header_module,
    namespace_for_root,
    scan_all_includes,
)
from core.common.utils import save_text
from core.planning.package_planner import _condensation_waves

DEFAULT_DEP_LAYERS_JSON = "dependency_layers.json"
DEFAULT_DEP_LAYERS_MD = "dependency_layers.md"
SCHEMA_VERSION = 1


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_dependency_layers_payload(
    *,
    inventory: HeaderInventoryReport,
    dep_graph: HeaderDependencyGraphReport,
) -> dict:
    """构建整包严格依赖分层 payload（不看迁移状态、不调模型）。"""
    namespace = namespace_for_root(inventory.header_root)
    header_root = Path(inventory.header_root)
    known_headers = {entry.relative_path for entry in inventory.headers}
    all_headers = sorted(known_headers)

    # 库内依赖边（include ∪ symbol，已解析到已知头）——决定分层；保证每个头都有键。
    in_package: dict[str, list[str]] = {
        entry.header: list(entry.dependencies) for entry in dep_graph.graph
    }
    for header in all_headers:
        in_package.setdefault(header, [])

    # 严格分层（SCC 凝聚 + 0-based 最长路分层；环成员同层）。复用 package_planner 的实现。
    header_layer, comp_id, components = _condensation_waves(all_headers, in_package)

    def _detail(header: str) -> dict:
        try:
            text = (header_root / header).read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        scan = scan_all_includes(text)
        conditional_targets = set(scan.conditional)

        in_pkg_deps = sorted(in_package.get(header, []))
        # 外部依赖 = 所有 active include 里「无法解析为已知库内头」的那些（系统头 + 未知命名空间头）。
        external: list[str] = []
        for inc in scan.active:
            rel = include_to_header_relpath(inc, namespace)
            if rel is None or rel not in known_headers:
                external.append(inc)
        external = sorted(set(external))

        # 条件依赖标注（仅在 #if 分支内被包含的）：库内用 namespace 还原为 relpath 比对。
        conditional_in_pkg = sorted(
            {
                rel
                for inc in conditional_targets
                if (rel := include_to_header_relpath(inc, namespace)) in known_headers
            }
        )
        conditional_external = sorted(t for t in conditional_targets if t in set(external))

        members = components[comp_id[header]]
        in_cycle = len(members) > 1
        return {
            "header": header,
            "include": f"{namespace}/{header}",
            "module": infer_header_module(header),
            "layer": header_layer[header],
            "in_cycle": in_cycle,
            "cycle_members": sorted(members) if in_cycle else [],
            "in_package_dependencies": in_pkg_deps,
            "external_dependencies": external,
            "conditional_in_package_dependencies": conditional_in_pkg,
            "conditional_external_dependencies": conditional_external,
            "in_package_dependency_count": len(in_pkg_deps),
            "external_dependency_count": len(external),
        }

    details = {header: _detail(header) for header in all_headers}

    by_layer: dict[int, list[str]] = defaultdict(list)
    for header in all_headers:
        by_layer[header_layer[header]].append(header)

    layers: list[dict] = []
    for level in sorted(by_layer):
        headers = sorted(by_layer[level], key=lambda h: (details[h]["module"], h))
        layers.append(
            {
                "layer": level,
                "header_count": len(headers),
                "contains_cycle": any(details[h]["in_cycle"] for h in headers),
                "headers": [details[h] for h in headers],
            }
        )

    cycles = sorted(
        (sorted(comp) for comp in components if len(comp) > 1),
        key=lambda comp: (len(comp), comp),
    )
    external_kinds = sorted({e for d in details.values() for e in d["external_dependencies"]})

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_iso(),
        "cccl_repo": inventory.cccl_repo,
        "header_root": inventory.header_root,
        "namespace": namespace,
        "summary": {
            "total_headers": len(all_headers),
            "layer_count": len(layers),
            "max_layer": (len(layers) - 1) if layers else 0,
            "cycle_count": len(cycles),
            "zero_in_package_dependency_headers": len(by_layer.get(0, [])),
            "distinct_external_dependency_count": len(external_kinds),
        },
        "layers": layers,
        "cycles": cycles,
        "distinct_external_dependencies": external_kinds,
    }


# --------------------------------------------------------------------------- #
# Markdown
# --------------------------------------------------------------------------- #
def _fmt_deps(deps: list[str], conditional: set[str]) -> str:
    if not deps:
        return "(none)"
    return ", ".join(f"`{d}`{' ⟂cond' if d in conditional else ''}" for d in deps)


def layers_to_markdown(payload: dict, *, json_name: str = DEFAULT_DEP_LAYERS_JSON) -> str:
    summary = payload["summary"]
    lines: list[str] = []
    lines.append("# Package Dependency Layers (strict topological)")
    lines.append("")
    lines.append(f"- generated_at: `{payload.get('generated_at', '')}`")
    lines.append(f"- cccl_repo: `{payload['cccl_repo']}`")
    lines.append(f"- header_root: `{payload['header_root']}`")
    lines.append(f"- namespace: `{payload['namespace']}`")
    lines.append(f"- companion_json: `outputs/plans/{json_name}`")
    lines.append(
        f"- headers: {summary['total_headers']}, layers: {summary['layer_count']}, "
        f"cycles: {summary['cycle_count']}, "
        f"layer-0 (zero in-package deps): {summary['zero_in_package_dependency_headers']}, "
        f"distinct external deps: {summary['distinct_external_dependency_count']}"
    )
    lines.append("")
    lines.append("> **分层口径**：Layer 0 = 库内零依赖头（优先迁移）。Layer N 只依赖 Layer < N。")
    lines.append("> 每个头列出全部依赖：`in-package`（决定分层）与 `external`（系统/外部头，仅列出，"
                 "不参与分层——它们不是迁移目标）。`⟂cond` = 仅在某个 `#if` 条件分支内被包含。")
    lines.append("> 处于依赖环（SCC）的头同层并标 `⟲`，需作为一组一起迁移。")
    lines.append("")

    for layer in payload.get("layers") or []:
        flag = " ⟲ contains cycle" if layer.get("contains_cycle") else ""
        lines.append(f"## Layer {layer['layer']} ({layer['header_count']} headers){flag}")
        lines.append("")
        for item in layer.get("headers") or []:
            cyc = " ⟲" if item.get("in_cycle") else ""
            lines.append(f"- `{item['header']}`  _({item['module']})_{cyc}")
            lines.append(
                "    - in-package: "
                + _fmt_deps(
                    item["in_package_dependencies"],
                    set(item.get("conditional_in_package_dependencies") or []),
                )
            )
            lines.append(
                "    - external: "
                + _fmt_deps(
                    item["external_dependencies"],
                    set(item.get("conditional_external_dependencies") or []),
                )
            )
            if item.get("in_cycle"):
                lines.append(f"    - cycle with: {', '.join(f'`{m}`' for m in item['cycle_members'])}")
        lines.append("")

    if payload.get("cycles"):
        lines.append(f"## Dependency cycles ({summary['cycle_count']})")
        lines.append("")
        for cycle in payload["cycles"]:
            lines.append(f"- {' ⟷ '.join(f'`{m}`' for m in cycle)}")
        lines.append("")

    return "\n".join(lines)


def write_dependency_layers(
    payload: dict,
    output_dir: str | Path,
    *,
    json_name: str = DEFAULT_DEP_LAYERS_JSON,
    md_name: str = DEFAULT_DEP_LAYERS_MD,
) -> tuple[Path, Path]:
    for name in (json_name, md_name):
        candidate = Path(name)
        if candidate.is_absolute() or len(candidate.parts) != 1:
            raise ValueError("dependency layers filename must be a file name under outputs/")
    out = Path(output_dir)
    json_path = out / json_name
    md_path = out / md_name
    save_text(json_path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    save_text(md_path, layers_to_markdown(payload, json_name=json_name) + "\n")
    return json_path, md_path
