"""迁移产物「自包含编译」校验门（roadmap R1.3 落地）。

动机：闭包按 leaf-first 迁移后，一个头是否真的能 `#include` 通，过去要等到 kernel
cannsim 阶段才暴露——典型报错：

    fatal error: 'asc/std/__utility/pair.h' file not found

本模块把这步前移到**最便宜的阶段**：把目标头单独包成一个翻译单元，用
`g++ -fsyntax-only -std=c++17 -I <include_root>` 编一次，专门抓「缺依赖 / include 路径
不一致」。它是确定性的（不调用模型），并能把 *file not found* 的依赖名单独抽出来，
让闭包据此判断「还差哪个依赖头没迁」。

设计取舍：
  * **无编译器即跳过**（`available=False`），不在没有 g++ 的开发机/CI 上误判失败；
  * 只做 `-fsyntax-only`（不链接、不实例化运行），秒级返回；
  * 既可被闭包当**确定性门**调用，也复用 `agent_tools.host_syntax_check` 之外的能力，
    给模型一个「落盘前自检包含关系」的事实源。
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

# 编译器报「找不到头」的两种典型措辞（gcc / clang）。
_MISSING_INCLUDE_RE = re.compile(
    r"(?:fatal error|error):\s*['\"<]?([^'\">\n]+\.h(?:pp)?)['\">]?\s*"
    r"(?::|\s)*(?:No such file or directory|file not found)",
    re.IGNORECASE,
)

DEFAULT_INCLUDE_ROOT_REL = "asc-stl/include"


@dataclass
class IncludeCheckResult:
    target_relpath: str
    include_directive: str = ""
    compiler: str = "g++"
    available: bool = True       # 编译器是否可用
    ran: bool = False            # 是否真的编了一次
    ok: bool = False             # available 且 returncode == 0
    returncode: int | None = None
    missing_includes: list[str] = field(default_factory=list)
    diagnostics: str = ""

    def to_dict(self) -> dict:
        return {
            "available": self.available,
            "compiler": self.compiler,
            "diagnostics": self.diagnostics,
            "include_directive": self.include_directive,
            "missing_includes": list(self.missing_includes),
            "ok": self.ok,
            "ran": self.ran,
            "returncode": self.returncode,
            "target_relpath": self.target_relpath,
        }


def include_directive_for(target_relpath: str, include_root_rel: str = DEFAULT_INCLUDE_ROOT_REL) -> str:
    """从目标头相对仓根的路径推导其公开 include 路径。

    `asc-stl/include/asc/std/__algorithm/min.h` --(去掉 include 根)--> `asc/std/__algorithm/min.h`
    """
    rel = target_relpath.replace("\\", "/").lstrip("/")
    prefix = include_root_rel.replace("\\", "/").strip("/") + "/"
    if rel.startswith(prefix):
        return rel[len(prefix):]
    return rel


def parse_missing_includes(diagnostics: str) -> list[str]:
    """从编译诊断里抽出「找不到」的头文件名（去重、保序）。"""
    seen: list[str] = []
    for match in _MISSING_INCLUDE_RE.finditer(diagnostics or ""):
        name = match.group(1).strip()
        if name and name not in seen:
            seen.append(name)
    return seen


def verify_header_self_contained(
    *,
    target_repo: str | Path,
    target_relpath: str,
    include_dirs: list[str | Path] | None = None,
    include_root_rel: str = DEFAULT_INCLUDE_ROOT_REL,
    gpp_bin: str = "g++",
    std: str = "c++17",
    timeout: int = 60,
    extra_defines: list[str] | None = None,
) -> IncludeCheckResult:
    """把目标头单独包成一个 TU 做 `-fsyntax-only` 自包含编译。

    include_dirs 缺省取 `<target_repo>/<include_root_rel>`（公开 include 根）。可显式传入
    以镜像 kernel 侧的 include 子集（host/kernel 两侧解析口径不一致是已知坑）。
    """
    target_repo = Path(target_repo)
    directive = include_directive_for(target_relpath, include_root_rel)
    result = IncludeCheckResult(target_relpath=target_relpath, include_directive=directive, compiler=gpp_bin)

    if not shutil.which(gpp_bin):
        result.available = False
        result.diagnostics = f"[verify_includes] 未找到编译器 {gpp_bin}，跳过自包含校验。"
        return result

    if include_dirs is None:
        include_dirs = [target_repo / include_root_rel]

    target_file = target_repo / target_relpath
    if not target_file.is_file():
        result.ran = False
        result.diagnostics = f"[verify_includes] 目标头不存在: {target_file}"
        return result

    with tempfile.TemporaryDirectory() as td:
        tu = Path(td) / "self_contained_tu.cpp"
        # 包两次以顺带验证 header guard 幂等（重复 include 不应重定义）。
        tu.write_text(
            f'#include "{directive}"\n#include "{directive}"\nint main() {{ return 0; }}\n',
            encoding="utf-8",
        )
        cmd = [gpp_bin, "-fsyntax-only", f"-std={std}"]
        for define in extra_defines or []:
            cmd.append(f"-D{define}")
        for inc in include_dirs:
            cmd += ["-I", str(inc)]
        cmd.append(str(tu))
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            result.ran = True
            result.returncode = None
            result.diagnostics = f"[verify_includes] 编译超时（>{timeout}s）"
            return result

    result.ran = True
    result.returncode = proc.returncode
    result.diagnostics = (proc.stderr or proc.stdout or "").strip()
    result.ok = proc.returncode == 0
    if not result.ok:
        result.missing_includes = parse_missing_includes(result.diagnostics)
    return result
