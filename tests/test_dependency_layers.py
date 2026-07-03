"""整包严格依赖分层的单元测试（确定性、离线）。"""

from core.analysis.dep_graph import build_dependency_graph_report
from core.analysis.inventory import scan_all_includes, scan_header_inventory
from core.planning.dependency_layers import (
    build_dependency_layers_payload,
    layers_to_markdown,
)


# --------------------------------------------------------------------------- #
# scan_all_includes: 系统头与库内头都要被捕获；#if 0 死分支丢弃；空格容忍
# --------------------------------------------------------------------------- #
def test_scan_all_includes_captures_system_and_in_tree():
    text = (
        "#include <cuda/std/detail/__config>\n"
        "#  include <errno.h>\n"            # 空格写法
        '#include "local/helper.h"\n'
        "#if 0\n#include <dead.h>\n#endif\n"  # 死分支
    )
    scan = scan_all_includes(text)
    assert "errno.h" in scan.active
    assert "cuda/std/detail/__config" in scan.active
    assert "local/helper.h" in scan.active
    assert "dead.h" in scan.dead and "dead.h" not in scan.active


def test_scan_all_includes_conditional_branch():
    text = "#if defined(__linux__)\n#include <unistd.h>\n#endif\n"
    scan = scan_all_includes(text)
    assert "unistd.h" in scan.active        # 未知宏 → 过包含
    assert "unistd.h" in scan.conditional   # 但标记为条件依赖


# --------------------------------------------------------------------------- #
# 分层：用一个临时小型 CCCL 树端到端验证拓扑层 + 全量依赖列举
# --------------------------------------------------------------------------- #
def _write(root, rel, body):
    p = root / "libcudacxx" / "include" / "cuda" / "std" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def _payload_for(tmp_path):
    # 依赖链：leaf.h (零依赖, 但含系统头) <- mid.h <- top.h ；外加一个独立 solo.h
    _write(tmp_path, "__x/leaf.h", "#ifndef L\n#define L\n#include <errno.h>\n#endif\n")
    _write(
        tmp_path,
        "__x/mid.h",
        "#ifndef M\n#define M\n#include <cuda/std/__x/leaf.h>\n#include <vector>\n#endif\n",
    )
    _write(tmp_path, "__x/top.h", "#ifndef T\n#define T\n#include <cuda/std/__x/mid.h>\n#endif\n")
    _write(tmp_path, "__x/solo.h", "#ifndef S\n#define S\n#endif\n")

    inventory = scan_header_inventory(tmp_path)
    dep_graph = build_dependency_graph_report(inventory)
    return build_dependency_layers_payload(inventory=inventory, dep_graph=dep_graph)


def _layer_of(payload, header):
    for layer in payload["layers"]:
        for item in layer["headers"]:
            if item["header"] == header:
                return layer["layer"], item
    raise AssertionError(f"{header} not found")


def test_strict_layering_orders_chain(tmp_path):
    payload = _payload_for(tmp_path)
    l_leaf, _ = _layer_of(payload, "__x/leaf.h")
    l_mid, _ = _layer_of(payload, "__x/mid.h")
    l_top, _ = _layer_of(payload, "__x/top.h")
    l_solo, _ = _layer_of(payload, "__x/solo.h")
    assert l_leaf == 0           # 零库内依赖（即便有系统头 errno.h）
    assert l_solo == 0
    assert l_mid == l_leaf + 1   # 只依赖 leaf
    assert l_top == l_mid + 1    # 只依赖 mid


def test_full_dependency_listing(tmp_path):
    payload = _payload_for(tmp_path)
    _, leaf = _layer_of(payload, "__x/leaf.h")
    _, mid = _layer_of(payload, "__x/mid.h")

    # leaf：库内零依赖，但系统头 errno.h 必须被列在 external
    assert leaf["in_package_dependencies"] == []
    assert "errno.h" in leaf["external_dependencies"]

    # mid：库内依赖 leaf；系统头 <vector> 在 external
    assert "__x/leaf.h" in mid["in_package_dependencies"]
    assert "vector" in mid["external_dependencies"]
    assert "__x/leaf.h" not in mid["external_dependencies"]


def test_summary_and_markdown_render(tmp_path):
    payload = _payload_for(tmp_path)
    assert payload["summary"]["total_headers"] == 4
    assert payload["summary"]["zero_in_package_dependency_headers"] == 2  # leaf + solo
    assert "errno.h" in payload["distinct_external_dependencies"]

    md = layers_to_markdown(payload)
    assert "# Package Dependency Layers (strict topological)" in md
    assert "## Layer 0" in md
    assert "errno.h" in md           # 系统依赖出现在 MD
    assert "`__x/leaf.h`" in md
