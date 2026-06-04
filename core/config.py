"""配置系统（ASC_agent / cccl-to-accl-v3 的核心改进）。

设计目标：彻底消除 v2 里的硬编码（conda 路径、用户目录、工具版本、
hook 检查文案、__cccl→__accl 这种隐式重命名等）。

加载顺序（后者覆盖前者）：
    1. 内置 DEFAULTS
    2. config/settings.yaml（用户可选，缺省项自动回退到 DEFAULTS）
    3. 运行期注入变量 / CLI 覆盖

所有字符串里的 ${VAR} 与 ${VAR:-default} 都会被展开，可引用：
    - 进程环境变量
    - 注入变量 PROJECT_ROOT / HOME
"""

from __future__ import annotations

import copy
import os
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import yaml

# ${VAR} 或 ${VAR:-default}；只匹配最内层（不含花括号），便于处理嵌套默认值
_ENV_PATTERN = re.compile(r"\$\{([^{}]+)\}")


# --------------------------------------------------------------------------- #
# 内置默认配置：用户的 settings.yaml 只需覆盖关心的字段
# --------------------------------------------------------------------------- #
DEFAULTS: dict[str, Any] = {
    "project": {"name": "ASC_agent"},
    "paths": {
        # 源仓库（CCCL）：默认放在项目内 repos/cccl，可用 CCCL_REPO 覆盖
        "cccl_repo": "${CCCL_REPO:-${PROJECT_ROOT}/repos/cccl}",
        # 目标仓库（ACCL）：默认放在项目内 repos/accl，可用 ACCL_REPO 覆盖
        # 这里已把 mylearn 的 host/kernel 测试链路整合进项目，因此目标仓库
        # 不再是外部的 mylearn，而是项目内的 repos/accl。
        "accl_repo": "${ACCL_REPO:-${PROJECT_ROOT}/repos/accl}",
        # 相对则相对于 PROJECT_ROOT
        "output_dir": "outputs",
    },
    # 路径与命名映射规则（v2 里这部分是写死/缺失的）
    "mapping": {
        "source_repo_prefix": "libcudacxx/include/cuda/std",
        "target_repo_prefix": "libascendcxx/include/ascend/std",
        # CCCL 侧测试树（与真实 libcudacxx 一致）。算子头 <op>.h 的测试源约定为
        # <cccl_test_prefix>/<同样的子路径段>/<op>.pass.cpp。用于「同步迁移测试代码」。
        "cccl_test_prefix": "libcudacxx/test/std",
        "cccl_test_suffix": ".pass.cpp",
        # 对相对路径里的每一段做替换，例如 __cccl -> __accl
        # 这正是 v2 缺失、导致 header guard 与示例对不上的地方
        "segment_substitutions": [
            {"from": "__cccl", "to": "__accl"},
        ],
        "module_hint_fallback": "generic",
    },
    "model": {
        "provider": "zhipu",          # zhipu | mock
        "model_name": "glm-5",        # 可改成 glm-5.1 / glm-4.6 等
        "api_key_env": "ZHIPU_API_KEY",
        # OpenAI 兼容的 chat/completions 接口地址
        "base_url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        "temperature": 0.6,
        "max_tokens": 65536,
        "thinking": False,            # 置 true 时请求体加 {"thinking": {"type": "enabled"}}
        "response_format_json": True, # 要求模型直接返回 JSON 对象
        "stream": True,               # 流式调用；配合 --show-model-io 可实时回显
    },
    "repo_verify": {
        "conda_sh": "",               # 留空则自动探测
        "conda_env": "asc_cccl_env",
        "clang_format_bin": "clang-format",   # 不再写死 clang-format-14
        "push_remote": "origin",
        "base_branch": "develop",
        "branch_prefix": "feature/ai",
        "commit_message_template": "add {filename}",
        "sign_off": True,
        "only_add_target_file": True,         # git add 仅目标文件，避免污染
        "require_clean_worktree": True,
        # hook 检查文案改为可配置；不再把具体英文写死在 Python 里
        "checks": [
            {
                "name": "license",
                "pattern": r"Add Apache 2\.0 license header.*Passed",
                "required": True,
            },
            {
                "name": "style",
                "pattern": r"CANN code style check \(clang-format \+ cpplint\).*Passed",
                "required": True,
            },
        ],
    },
    "retry": {"max_fix_rounds": 5},
    "tests": {
        # kernel 仿真(cannsim/camodel)是 cycle-accurate 的，单次可达数分钟；
        # 默认给足超时，避免被调用方误杀（历史上 540s 就被 timeout 杀过）。
        "kernel_timeout_sec": 1200,
        "host_timeout_sec": 600,
        # 快速档：把 kernel 仿真 workload 从 8×2048 降到 1 核 1 tile(64 元素)，
        # camodel 数十秒即可跑完，适合 CI/冒烟。默认关闭；最终验证用完整档。
        "fast_kernel": False,
    },
    "examples": {
        "example_1": {
            "cccl": "${PROJECT_ROOT}/examples/headers/max.cccl.h",
            "accl": "${PROJECT_ROOT}/examples/headers/max.accl.h",
        },
        "example_2": {
            "cccl": "${PROJECT_ROOT}/examples/headers/os.cccl.h",
            "accl": "${PROJECT_ROOT}/examples/headers/os.accl.h",
        },
    },
    # 测试迁移的成功示例对（CCCL 测试 → ACCL host 测试 + kernel_spec）。
    # 各覆盖一种算子形态：example_1=二元返回值(max)，example_2=原地 void(swap)。
    "test_examples": {
        "example_1": {
            "cccl_test": "${PROJECT_ROOT}/examples/tests/max.cccl.pass.cpp",
            "accl_host": "${PROJECT_ROOT}/examples/tests/max.accl_host.cpp",
            "accl_kernel_spec": "${PROJECT_ROOT}/examples/tests/max.accl_kernel_spec.json",
        },
        "example_2": {
            "cccl_test": "${PROJECT_ROOT}/examples/tests/swap.cccl.pass.cpp",
            "accl_host": "${PROJECT_ROOT}/examples/tests/swap.accl_host.cpp",
            "accl_kernel_spec": "${PROJECT_ROOT}/examples/tests/swap.accl_kernel_spec.json",
        },
    },
    # 模型输出归一化开关（v2 里是写死的三条正则）
    "normalize": {
        "fix_directive_spacing": True,
        "ensure_trailing_newline": True,
    },
}


# --------------------------------------------------------------------------- #
# 工具函数
# --------------------------------------------------------------------------- #
def _expand_str(value: str, variables: dict[str, str]) -> str:
    """展开 ${VAR} / ${VAR:-default}，支持嵌套；未解析到的原样保留。"""

    def repl(match: re.Match) -> str:
        expr = match.group(1)
        if ":-" in expr:
            name, default = expr.split(":-", 1)
        else:
            name, default = expr, None
        name = name.strip()
        resolved = variables.get(name, os.environ.get(name))
        if resolved is None:
            if default is not None:
                return default
            return match.group(0)  # 保留原样，避免意外报错
        return resolved

    prev = None
    out = value
    # 循环展开以处理 ${A:-${B}} 这类嵌套
    while prev != out:
        prev = out
        out = _ENV_PATTERN.sub(repl, out)
    return out


def _expand_tree(obj: Any, variables: dict[str, str]) -> Any:
    if isinstance(obj, str):
        return _expand_str(obj, variables)
    if isinstance(obj, dict):
        return {k: _expand_tree(v, variables) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_tree(v, variables) for v in obj]
    return obj


def _deep_merge(base: dict, override: Optional[dict]) -> dict:
    """深合并；list 类型直接整体覆盖（如 checks 由用户整组提供）。"""
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def detect_conda_sh() -> str:
    """自动探测 conda.sh，找不到返回空字符串（表示不激活 conda）。"""
    candidates: list[Path] = []

    conda_exe = os.environ.get("CONDA_EXE")
    if conda_exe:
        # .../miniconda3/bin/conda -> .../miniconda3/etc/profile.d/conda.sh
        base = Path(conda_exe).resolve().parent.parent
        candidates.append(base / "etc" / "profile.d" / "conda.sh")

    conda_prefix = os.environ.get("CONDA_PREFIX")
    if conda_prefix:
        candidates.append(Path(conda_prefix) / "etc" / "profile.d" / "conda.sh")

    home = Path.home()
    for base in (
        home / "miniconda3",
        home / "anaconda3",
        home / "miniforge3",
        Path("/opt/conda"),
        Path("/opt/miniconda3"),
    ):
        candidates.append(base / "etc" / "profile.d" / "conda.sh")

    for cand in candidates:
        if cand.exists():
            return str(cand)
    return ""


# --------------------------------------------------------------------------- #
# Config 对象
# --------------------------------------------------------------------------- #
@dataclass
class Config:
    raw: dict
    project_root: Path

    # ----- 加载 ----- #
    @classmethod
    def load(
        cls,
        settings_path: Optional[Path],
        project_root: Path,
        extra_vars: Optional[dict[str, str]] = None,
        overrides: Optional[dict] = None,
    ) -> "Config":
        project_root = Path(project_root).resolve()

        user: dict = {}
        if settings_path and Path(settings_path).exists():
            loaded = yaml.safe_load(Path(settings_path).read_text(encoding="utf-8"))
            user = loaded or {}

        merged = _deep_merge(DEFAULTS, user)
        if overrides:
            merged = _deep_merge(merged, overrides)

        # 向后兼容：旧配置/测试用 paths.mylearn_repo 表示目标仓库，
        # 现统一为 paths.accl_repo。只有用户显式提供时才映射（DEFAULTS 里没有此键）。
        paths = merged.get("paths", {})
        if paths.get("mylearn_repo"):
            paths["accl_repo"] = paths["mylearn_repo"]

        variables = {
            "PROJECT_ROOT": str(project_root),
            "HOME": str(Path.home()),
        }
        if extra_vars:
            variables.update(extra_vars)
        merged = _expand_tree(merged, variables)

        if not merged["repo_verify"].get("conda_sh"):
            merged["repo_verify"]["conda_sh"] = detect_conda_sh()

        cfg = cls(raw=merged, project_root=project_root)
        cfg.validate()
        return cfg

    # ----- 校验 ----- #
    def validate(self) -> None:
        m = self.raw["mapping"]
        if not m.get("source_repo_prefix") or not m.get("target_repo_prefix"):
            raise ValueError("mapping.source_repo_prefix / target_repo_prefix 不能为空")

        if int(self.raw["retry"]["max_fix_rounds"]) < 1:
            raise ValueError("retry.max_fix_rounds 必须 >= 1")

        if not self.raw["model"].get("model_name"):
            raise ValueError("model.model_name 不能为空")

        checks = self.raw["repo_verify"].get("checks")
        if not isinstance(checks, list) or not checks:
            raise ValueError("repo_verify.checks 必须是非空列表")
        for c in checks:
            if "name" not in c or "pattern" not in c:
                raise ValueError(f"repo_verify.checks 每项需包含 name 与 pattern: {c}")

    # ----- 便捷访问器 ----- #
    @property
    def output_dir(self) -> Path:
        raw = self.raw["paths"]["output_dir"]
        p = Path(raw)
        return p if p.is_absolute() else (self.project_root / p)

    @property
    def cccl_repo(self) -> str:
        return self.raw["paths"]["cccl_repo"]

    @property
    def accl_repo(self) -> str:
        return self.raw["paths"]["accl_repo"]

    @property
    def target_repo(self) -> str:
        """目标（ACCL）仓库根目录。"""
        return self.raw["paths"]["accl_repo"]

    @property
    def mylearn_repo(self) -> str:
        """向后兼容别名：等价于 target_repo / accl_repo。"""
        return self.target_repo

    @property
    def kernel_timeout_sec(self) -> int:
        return int(self.raw.get("tests", {}).get("kernel_timeout_sec", 1200))

    @property
    def host_timeout_sec(self) -> int:
        return int(self.raw.get("tests", {}).get("host_timeout_sec", 600))

    @property
    def fast_kernel(self) -> bool:
        return bool(self.raw.get("tests", {}).get("fast_kernel", False))

    @property
    def source_repo_prefix(self) -> str:
        return self.raw["mapping"]["source_repo_prefix"]

    @property
    def target_repo_prefix(self) -> str:
        return self.raw["mapping"]["target_repo_prefix"]

    @property
    def segment_substitutions(self) -> list[dict]:
        return self.raw["mapping"].get("segment_substitutions", [])

    @property
    def cccl_test_prefix(self) -> str:
        return self.raw["mapping"].get("cccl_test_prefix", "libcudacxx/test/std")

    @property
    def cccl_test_suffix(self) -> str:
        return self.raw["mapping"].get("cccl_test_suffix", ".pass.cpp")

    @property
    def module_hint_fallback(self) -> str:
        return self.raw["mapping"].get("module_hint_fallback", "generic")

    @property
    def model_provider(self) -> str:
        return self.raw["model"].get("provider", "zhipu")

    @property
    def model_name(self) -> str:
        return self.raw["model"]["model_name"]

    @property
    def api_key_env(self) -> str:
        return self.raw["model"].get("api_key_env", "ZHIPU_API_KEY")

    @property
    def model_base_url(self) -> str:
        return self.raw["model"].get(
            "base_url", "https://open.bigmodel.cn/api/paas/v4/chat/completions"
        )

    @property
    def model_temperature(self) -> float:
        return float(self.raw["model"].get("temperature", 0.6))

    @property
    def model_max_tokens(self) -> int:
        return int(self.raw["model"].get("max_tokens", 65536))

    @property
    def model_thinking(self) -> bool:
        return bool(self.raw["model"].get("thinking", False))

    @property
    def model_response_format_json(self) -> bool:
        return bool(self.raw["model"].get("response_format_json", True))

    @property
    def model_stream(self) -> bool:
        return bool(self.raw["model"].get("stream", True))

    @property
    def repo_verify(self) -> dict:
        return self.raw["repo_verify"]

    @property
    def max_fix_rounds(self) -> int:
        return int(self.raw["retry"]["max_fix_rounds"])

    @property
    def normalize_options(self) -> dict:
        return self.raw.get("normalize", {})

    def skill_path(self, name: str) -> Path:
        return self.project_root / "skills" / name

    def example_paths(self) -> dict:
        return self.raw["examples"]

    def test_example_paths(self) -> dict:
        return self.raw.get("test_examples", {})

    # ----- shell 构造（统一加 conda 前缀 + 安全转义） ----- #
    def build_shell_script(self, body: str, cd_repo: bool = True) -> str:
        """生成在目标提交环境下执行的 bash 脚本，所有路径用 shlex.quote 转义。"""
        rv = self.repo_verify
        lines = ["set -e"]
        conda_sh = rv.get("conda_sh")
        conda_env = rv.get("conda_env")
        if conda_sh:
            lines.append(f"source {shlex.quote(conda_sh)}")
            if conda_env:
                lines.append(f"conda activate {shlex.quote(conda_env)}")
        if cd_repo:
            lines.append(f"cd {shlex.quote(self.target_repo)}")
        lines.append(body)
        return "\n".join(lines)
