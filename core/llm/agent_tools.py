"""模型可调用的「取证 + 自检」工具层（P1）。

动机：当前修复链路是"单轮 prompt → JSON"的盲猜——模型看不到 sibling 头文件、查不到
宏/符号的真实定义、无法在落盘前自检产物、几万行日志只能整块塞回。这里把四件最有用的
能力封装成有界、可沙箱、可单测的工具，让修复模型从"盲猜"变"可取证 + 可自验证"：

    * read_repo_file   —— 按需读目标仓任意头/源（如 __config、sibling 算子）
    * grep_repo        —— 查符号/宏定义（如 _ASC_AICORE_FN 到底怎么定义）
    * host_syntax_check—— host 产物先 g++ -fsyntax-only 自检，省一整轮往返
    * extract_error_lines —— 从大日志里只抽 error/warning 行回喂

所有文件路径都被限制在 target_repo / output_dir 根下，禁止 ``..`` 越界。dispatch 永不抛
异常，错误以字符串返回（作为工具消息回给模型），保证调用循环健壮。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

# OpenAI 兼容的 tools 声明（GLM 支持）。供 model_client 在请求里带上。
TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "read_repo_file",
            "description": "读取目标 ACCL 仓库内的一个文件（如 sibling 算子头、asc/std/__config）。"
            "用于在不把所有上下文塞进 prompt 的情况下，按需查看真实代码。",
            "parameters": {
                "type": "object",
                "properties": {
                    "relpath": {
                        "type": "string",
                        "description": "相对目标仓库根的路径，如 asc-stl/include/asc/std/__config",
                    }
                },
                "required": ["relpath"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep_repo",
            "description": "在目标 ACCL 仓库内按正则搜索，定位宏/符号/函数的真实定义"
            "（如 _ASC_AICORE_FN、_ASC_STD_BEGIN）。返回匹配的文件:行号:内容。",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Python 正则表达式"},
                    "glob": {
                        "type": "string",
                        "description": "可选，限制文件名通配，如 *.h（默认搜常见 C/C++ 源与头）",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "host_syntax_check",
            "description": "用 g++ -fsyntax-only -std=c++17 对一段 host C++ 代码做编译期语法/语义自检"
            "（自动带上 ACCL include 路径）。返回是否通过及编译器诊断。落盘前自验证 host 测试/头文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "完整的 C++ 源码文本"}
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "extract_error_lines",
            "description": "从一份大日志里抽取真正的 error/warning 行及其上下文（host/kernel 日志可达数万行）。"
            "传 log_name（outputs 下的日志文件名）或直接传 text。",
            "parameters": {
                "type": "object",
                "properties": {
                    "log_name": {"type": "string", "description": "outputs/ 下的日志文件名，如 kernel_test_sort3.log"},
                    "text": {"type": "string", "description": "或直接给日志文本"},
                },
            },
        },
    },
]

_ERROR_LINE_RE = re.compile(
    r"(?:^|\b)(error:|错误|undefined reference|Mismatch at|FAILED|CMake Error|"
    r"FileNotFoundError|fatal error|Error \d|warning:|cannot|No such file)",
    re.IGNORECASE,
)


def distill_error_lines(
    text: str, *, context: int = 2, max_chars: int = 20000, tail_lines: int = 20
) -> str:
    """从大日志里抽取真正的 error/warning 行及其上下文，丢掉成片的噪音。

    两处复用同一份蒸馏逻辑（单一事实源）：
      * 模型主动调用的 `extract_error_lines` 工具；
      * 默认测试反馈构造（main._build_test_feedback_text）——避免把数万行日志按字节
        硬截断、反而把真正的报错截没了。
    无 error 特征时回退到日志末尾若干行（构建卡在中途时，尾部往往就是现场）。
    """
    if not text:
        return ""
    lines = text.splitlines()
    keep: set[int] = set()
    for i, line in enumerate(lines):
        if _ERROR_LINE_RE.search(line):
            for j in range(max(0, i - context), min(len(lines), i + context + 1)):
                keep.add(j)
    if not keep:
        return f"[未匹配到 error 特征，给出日志末尾 {tail_lines} 行]\n" + "\n".join(
            lines[-tail_lines:]
        )
    out: list[str] = []
    prev = -2
    for idx in sorted(keep):
        if idx != prev + 1:
            out.append("--")
        out.append(f"{idx + 1}: {lines[idx]}")
        prev = idx
    joined = "\n".join(out)
    return joined[:max_chars] + ("\n...[truncated]" if len(joined) > max_chars else "")

_DEFAULT_GREP_SUFFIXES = (".h", ".hpp", ".hh", ".cpp", ".cc", ".cxx", ".c", ".inc")
_SKIP_DIRS = {"build", ".git", "__pycache__", "cmake-build-debug"}


class AgentToolbox:
    """把工具执行限制在沙箱内；schemas() 给模型声明，dispatch() 执行。"""

    def __init__(
        self,
        target_repo: Path,
        output_dir: Path,
        *,
        host_include_dirs: list[Path] | None = None,
        max_read_bytes: int = 20000,
        max_grep_matches: int = 50,
        gpp_bin: str = "g++",
        compile_timeout: int = 60,
    ):
        self.target_repo = Path(target_repo).resolve()
        self.output_dir = Path(output_dir).resolve()
        self.host_include_dirs = [Path(p) for p in (host_include_dirs or [])]
        self.max_read_bytes = max_read_bytes
        self.max_grep_matches = max_grep_matches
        self.gpp_bin = gpp_bin
        self.compile_timeout = compile_timeout
        self.call_log: list[dict] = []

    # ----- schema ----- #
    @staticmethod
    def schemas() -> list[dict]:
        return TOOL_SCHEMAS

    # ----- 沙箱路径解析 ----- #
    @staticmethod
    def _resolve_within(base: Path, relpath: str) -> Path:
        base_r = base.resolve()
        target = (base_r / relpath).resolve()
        if target != base_r and base_r not in target.parents:
            raise ValueError(f"路径越界（禁止访问仓库外）：{relpath}")
        return target

    # ----- 工具实现 ----- #
    def read_repo_file(self, relpath: str) -> str:
        path = self._resolve_within(self.target_repo, relpath)
        if not path.is_file():
            return f"[read_repo_file] 文件不存在: {relpath}"
        data = path.read_text(encoding="utf-8", errors="replace")
        if len(data) > self.max_read_bytes:
            data = data[: self.max_read_bytes] + f"\n...[truncated, 共 {len(data)} 字符]"
        return data

    def grep_repo(self, pattern: str, glob: str | None = None) -> str:
        try:
            rx = re.compile(pattern)
        except re.error as exc:
            return f"[grep_repo] 正则无效: {exc}"
        matches: list[str] = []
        for path in self._iter_repo_files(glob):
            try:
                for i, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                    if rx.search(line):
                        rel = path.relative_to(self.target_repo)
                        matches.append(f"{rel}:{i}:{line.strip()[:200]}")
                        if len(matches) >= self.max_grep_matches:
                            matches.append(f"...[超过 {self.max_grep_matches} 条，已截断]")
                            return "\n".join(matches)
            except OSError:
                continue
        return "\n".join(matches) if matches else "[grep_repo] 无匹配"

    def _iter_repo_files(self, glob: str | None):
        for path in sorted(self.target_repo.rglob(glob or "*")):
            if not path.is_file():
                continue
            if any(part in _SKIP_DIRS for part in path.relative_to(self.target_repo).parts):
                continue
            if glob is None and path.suffix not in _DEFAULT_GREP_SUFFIXES:
                continue
            yield path

    def host_syntax_check(self, code: str) -> str:
        if not shutil.which(self.gpp_bin):
            return f"[host_syntax_check] 未找到编译器 {self.gpp_bin}，无法自检（跳过）。"
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "snippet.cpp"
            src.write_text(code, encoding="utf-8")
            cmd = [self.gpp_bin, "-fsyntax-only", "-std=c++17"]
            for inc in self.host_include_dirs:
                cmd += ["-I", str(inc)]
            cmd.append(str(src))
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=self.compile_timeout)
            except subprocess.TimeoutExpired:
                return f"[host_syntax_check] 编译超时（>{self.compile_timeout}s）"
            if proc.returncode == 0:
                diag = (proc.stderr or "").strip()
                return "OK：语法/语义检查通过。" + (f"\n[warnings]\n{diag}" if diag else "")
            return "FAILED：\n" + (proc.stderr or proc.stdout or "(无诊断输出)").strip()[: self.max_read_bytes]

    def extract_error_lines(self, log_name: str | None = None, text: str | None = None, context: int = 2) -> str:
        if text is None and log_name:
            try:
                path = self._resolve_within(self.output_dir, log_name)
                text = path.read_text(encoding="utf-8", errors="replace")
            except (ValueError, OSError) as exc:
                return f"[extract_error_lines] 无法读取日志 {log_name}: {exc}"
        if not text:
            return "[extract_error_lines] 未提供 log_name 或 text"
        return distill_error_lines(text, context=context, max_chars=self.max_read_bytes)

    # ----- 分发 ----- #
    def dispatch(self, name: str, arguments: dict) -> str:
        result = self._invoke(name, arguments)
        # 记录调用 + 结果摘要：让「模型是否/如何调用工具」可被审计（见 dump_call_log）。
        self.call_log.append(
            {"name": name, "arguments": arguments, "result_preview": str(result)[:300]}
        )
        return result

    def _invoke(self, name: str, arguments: dict) -> str:
        try:
            if name == "read_repo_file":
                return self.read_repo_file(str(arguments["relpath"]))
            if name == "grep_repo":
                return self.grep_repo(str(arguments["pattern"]), arguments.get("glob"))
            if name == "host_syntax_check":
                return self.host_syntax_check(str(arguments["code"]))
            if name == "extract_error_lines":
                return self.extract_error_lines(arguments.get("log_name"), arguments.get("text"))
            return f"[dispatch] 未知工具: {name}"
        except KeyError as exc:
            return f"[dispatch] 工具 {name} 缺少必填参数: {exc}"
        except Exception as exc:  # 工具失败不应中断对话
            return f"[dispatch] 工具 {name} 执行出错: {type(exc).__name__}: {exc}"

    def dump_call_log(self, path) -> None:
        """把工具调用记录落盘（name/arguments/result_preview + 总次数），便于事后审计。

        解决「只能靠模型在 notes 里自述是否调用了工具」的盲区——现在每个用工具的阶段都
        留下硬证据：count=0 即模型本阶段没调用任何工具。
        """
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {"count": len(self.call_log), "tool_calls": self.call_log}
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_toolbox(config):
    """按配置构建模型工具箱（取证 + host 自检）；不满足条件返回 None。

    单一事实源：迁移 / 测试迁移 / 测试反馈修复三条链路都经此构建，避免各处重复拼装。
    门槛：
      * `model.tools_enabled` 关闭 → None（保持「单轮 prompt→JSON」的旧行为）。
      * provider == mock → None（离线 mock 不需要真实工具，省去无谓的 tool 往返）。
    host_syntax_check 的 -I 指向 ACCL include 根，让模型能就地解析 `asc/std/...`。
    """
    if not getattr(config, "model_tools_enabled", False):
        return None
    if getattr(config, "model_provider", "") == "mock":
        return None
    include_dir = Path(config.target_repo) / "asc-stl" / "include"
    return AgentToolbox(
        target_repo=Path(config.target_repo),
        output_dir=config.output_dir,
        host_include_dirs=[include_dir],
    )


def parse_tool_arguments(raw) -> dict:
    """模型回传的 tool_call.arguments 可能是 JSON 字符串或已是 dict，统一成 dict。"""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            obj = json.loads(raw)
            return obj if isinstance(obj, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}
