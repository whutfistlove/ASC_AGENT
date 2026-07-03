"""``__host_stdlib/*`` 转发垫片的确定性内容校验门。

动机：CCCL 的 ``__host_stdlib/<X>`` 头是「host 编译时把系统 ``<X>`` 引进来」的转发垫片
（device 侧无宿主 STL，故 no-op）。迁移到 ASC-STL 的既定写法是：

    #if defined(__CCE__)        // device：无宿主 STL → no-op
    #define ASC_DEVICE_CODE
    #else                       // host：引入系统头
    #include <X>
    #endif

模型逐文件判断时，偶尔会把 host 分支整段丢掉、退化成「空壳」（实测 ``__host_stdlib/algorithm``
就曾漏掉 ``#include <algorithm>``）。空壳能通过 :mod:`core.testing.verify_includes` 的自包含
编译门（它确实自包含），所以这类回归不会被那道门抓到——它的征兆是「host 侧拿不到系统类型」，
要等到具体 host 测试用到 ``std::xxx`` 才暴露，而当前 host 测试又常被弱化成「只验 include 守卫」。

本模块补上这道缺口：纯词法、离线、确定性地要求 ``__host_stdlib/<X>`` 的迁移产物里出现
``#include <X>``（``X`` 取文件名，如 ``algorithm`` / ``numeric`` / ``math.h``）。

范围说明（保持确定性、避免误报）：只校验**系统头是否被转发**，不校验它落在 host 还是 device
分支——分支放错（误塞进 ``__CCE__`` 真分支）会在 host 自包含编译门 / host 测试里以缺类型暴露，
而「整段丢失」正是那两道门都抓不到、需要本门兜住的盲区。与 inventory / kernel_requirement 对齐：
纯词法、离线、确定性、可单测。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from core.testing.kernel_requirement import module_of

HOST_STDLIB_MODULE = "__host_stdlib"


@dataclass
class HostShimCheckResult:
    target_relpath: str
    applicable: bool = False      # 是否是 __host_stdlib/* 垫片（非垫片直接 applicable=False/ok=True）
    ok: bool = True               # 适用且通过校验
    expected_include: str = ""    # 期望转发的系统头名，如 "algorithm"
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "applicable": self.applicable,
            "expected_include": self.expected_include,
            "ok": self.ok,
            "reason": self.reason,
            "target_relpath": self.target_relpath,
        }


def is_host_stdlib_shim(target_relpath: str) -> bool:
    """relpath 是否属于 ``__host_stdlib`` 模块（转发垫片）。"""
    return module_of(target_relpath) == HOST_STDLIB_MODULE


def expected_system_header(target_relpath: str) -> str:
    """``__host_stdlib/<X>`` 转发的系统头名 = 文件名本身。

    无扩展名头（``algorithm`` / ``numeric`` / ``memory`` ...）与有扩展名头
    （``math.h`` / ``time.h``）都直接取 basename。
    """
    return PurePosixPath(str(target_relpath).replace("\\", "/")).name


def _forwards_system_header(code: str, name: str) -> bool:
    """逐行判断是否存在 ``#include <name>`` 预处理指令（容忍空白与行尾注释）。

    只认「该逻辑行本身就是 include 指令」，因此被 ``//`` / ``/* */`` 注释掉的写法不会误判为通过。
    """
    directive = re.compile(r"^\s*#\s*include\s*<\s*" + re.escape(name) + r"\s*>")
    in_block_comment = False
    for raw in code.splitlines():
        line = raw
        if in_block_comment:
            end = line.find("*/")
            if end == -1:
                continue
            line = line[end + 2:]
            in_block_comment = False
        # 去掉本行内的块注释片段，再去掉行尾行注释。
        line = re.sub(r"/\*.*?\*/", " ", line)
        if "/*" in line:  # 未闭合块注释：保留 /* 之前部分，标记跨行
            line = line[: line.index("/*")]
            in_block_comment = True
        line = re.sub(r"//.*$", "", line)
        if directive.match(line):
            return True
    return False


def check_host_stdlib_forwarding(target_relpath: str, migrated_text: str) -> HostShimCheckResult:
    """校验 ``__host_stdlib/<X>`` 迁移产物是否转发了系统 ``<X>``。

    非 ``__host_stdlib`` 头：``applicable=False, ok=True``（调用方据此跳过）。
    """
    result = HostShimCheckResult(target_relpath=target_relpath)
    if not is_host_stdlib_shim(target_relpath):
        return result

    name = expected_system_header(target_relpath)
    result.applicable = True
    result.expected_include = name
    if _forwards_system_header(migrated_text or "", name):
        result.ok = True
    else:
        result.ok = False
        result.reason = (
            f"__host_stdlib 转发垫片缺少 host 侧 `#include <{name}>`"
            f"（退化为空壳：能通过自包含编译，但 host 侧拿不到系统 <{name}>）"
        )
    return result
