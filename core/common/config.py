"""配置系统（ASC_agent / cccl-to-accl-v3 的核心改进）。

设计目标：彻底消除 v2 里的硬编码（conda 路径、用户目录、工具版本、
hook 检查文案、__cccl→__asc 这种隐式重命名等）。

加载顺序（后者覆盖前者）：
    1. 内置 DEFAULTS
    2. config/settings.yaml（用户可选，缺省项自动回退到 DEFAULTS）
    3. 运行期注入变量 / CLI 覆盖
    4. reference/symbol_mapping.yaml 的迁移策略（segment_substitutions / migration_policy）

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


# reference/symbol_mapping.yaml 是迁移策略的事实源；这里的 fallback 只用于临时测试项目或
# reference 缺失的降级场景，真实项目加载时会被 reference 覆盖。
_FALLBACK_SEGMENT_SUBSTITUTIONS = [{"from": "__cccl", "to": "__asc"}]
_FALLBACK_MIGRATION_POLICY: dict[str, Any] = {
    "deferred_upstream_support_prefixes": ["__cccl/", "__internal/", "__support/", "detail/"],
    "bootstrap_manual_coverage": {"detail/__config": "__config"},
    "target_only_compatibility_wrappers": ["__algorithm/swap.h", "__numeric/gcd.h", "__numeric/lcm.h"],
    "public_aggregation_headers": [
        "algorithm", "functional", "iterator", "numeric", "type_traits", "utility",
    ],
}


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
        # 可审计知识库（照搬自官方 cuda2ascend-simt：符号映射/语法/约束规则）。
        "reference_dir": "${PROJECT_ROOT}/reference",
    },
    # 路径与命名映射规则（v2 里这部分是写死/缺失的）
    "mapping": {
        "source_repo_prefix": "libcudacxx/include/cuda/std",
        "target_repo_prefix": "asc-stl/include/asc/std",
        # CCCL 侧测试树（与真实 libcudacxx 一致）。算子头 <op>.h 的测试源约定为
        # <cccl_test_prefix>/<同样的子路径段>/<op>.pass.cpp。用于「同步迁移测试代码」。
        "cccl_test_prefix": "libcudacxx/test/libcudacxx/std",
        "cccl_test_suffix": ".pass.cpp",
        # 由 reference/symbol_mapping.yaml 的 segment_substitutions 覆盖。
        "segment_substitutions": copy.deepcopy(_FALLBACK_SEGMENT_SUBSTITUTIONS),
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
        "draft_samples": 1,           # best-of-N 候选数；1=单发（默认，行为不变）
    },
    # few-shot 检索：按算子相关度从 examples/ 选最贴近的示例（示例库越大越受益）。
    "few_shot": {
        "retrieval": True,            # 关掉则回退到 examples 配置顺序
        "top_k": 2,
    },
    # 源码符号隐含依赖。真实项目会由 reference/symbol_mapping.yaml 覆盖。
    "dependency_analysis": {
        "symbol_dependencies": [],
    },
    "repo_verify": {
        "conda_sh": "",               # 留空则自动探测
        "conda_env": "accl",
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
        "kernel_soc_version": "Ascend950PR_9599",
        "kernel_cannsim_soc_version": "Ascend950",
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
    # 由 reference/symbol_mapping.yaml 的 migration_policy 覆盖。
    "migration_policy": copy.deepcopy(_FALLBACK_MIGRATION_POLICY),
}


# --------------------------------------------------------------------------- #
# 迁移策略（单一事实源；pipeline 与 migration_status 共用）
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class MigrationPolicy:
    deferred_upstream_support_prefixes: tuple[str, ...]
    bootstrap_manual_coverage: dict[str, str]
    target_only_compatibility_wrappers: frozenset[str]
    public_aggregation_headers: frozenset[str]

    @classmethod
    def from_raw(cls, raw: dict | None) -> "MigrationPolicy":
        raw = raw or {}
        base = _FALLBACK_MIGRATION_POLICY
        return cls(
            deferred_upstream_support_prefixes=tuple(
                raw.get("deferred_upstream_support_prefixes", base["deferred_upstream_support_prefixes"])
            ),
            bootstrap_manual_coverage=dict(
                raw.get("bootstrap_manual_coverage", base["bootstrap_manual_coverage"])
            ),
            target_only_compatibility_wrappers=frozenset(
                raw.get("target_only_compatibility_wrappers", base["target_only_compatibility_wrappers"])
            ),
            public_aggregation_headers=frozenset(
                raw.get("public_aggregation_headers", base["public_aggregation_headers"])
            ),
        )


def default_migration_policy() -> MigrationPolicy:
    """无 Config 上下文时（如 migration_status 的纯函数默认值）使用的降级策略。"""
    return MigrationPolicy.from_raw(None)


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


def _reference_policy_yaml(reference_dir: Path) -> dict:
    path = reference_dir / "symbol_mapping.yaml"
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise ValueError(f"无法读取 reference 策略文件: {path}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"reference 策略文件不是合法 YAML: {path}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"reference 策略文件顶层必须是 mapping: {path}")
    return data


def _segment_substitution_contract(items: list | None) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        src = item.get("from")
        dst = item.get("to")
        if src is not None and dst is not None:
            out.append({"from": str(src), "to": str(dst)})
    return out


def _migration_policy_contract(raw: dict | None) -> dict:
    policy = MigrationPolicy.from_raw(raw)
    return {
        "deferred_upstream_support_prefixes": list(policy.deferred_upstream_support_prefixes),
        "bootstrap_manual_coverage": dict(policy.bootstrap_manual_coverage),
        "target_only_compatibility_wrappers": sorted(policy.target_only_compatibility_wrappers),
        "public_aggregation_headers": sorted(policy.public_aggregation_headers),
    }


def _symbol_dependency_contract(items: list | None) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        symbol = item.get("symbol") or item.get("pattern")
        header = item.get("header")
        include = item.get("include")
        if not symbol or not (header or include):
            continue
        row = {
            "symbol": str(symbol),
            "kind": str(item.get("kind") or "symbol"),
        }
        if header:
            row["header"] = str(header)
        if include:
            row["include"] = str(include)
        out.append(row)
    return out


def _reference_migration_policy_raw(raw: dict) -> dict:
    """Return only runtime policy fields from reference YAML, dropping audit metadata."""
    return {
        "deferred_upstream_support_prefixes": list(
            raw.get(
                "deferred_upstream_support_prefixes",
                _FALLBACK_MIGRATION_POLICY["deferred_upstream_support_prefixes"],
            )
        ),
        "bootstrap_manual_coverage": dict(
            raw.get("bootstrap_manual_coverage", _FALLBACK_MIGRATION_POLICY["bootstrap_manual_coverage"])
        ),
        "target_only_compatibility_wrappers": list(
            raw.get(
                "target_only_compatibility_wrappers",
                _FALLBACK_MIGRATION_POLICY["target_only_compatibility_wrappers"],
            )
        ),
        "public_aggregation_headers": list(
            raw.get(
                "public_aggregation_headers",
                _FALLBACK_MIGRATION_POLICY["public_aggregation_headers"],
            )
        ),
    }


def _resolve_reference_dir(raw: dict, project_root: Path) -> Path:
    value = raw.get("paths", {}).get("reference_dir", str(project_root / "reference"))
    p = Path(str(value))
    return p if p.is_absolute() else project_root / p


def _apply_reference_strategy(raw: dict, project_root: Path) -> None:
    """Make reference/symbol_mapping.yaml the runtime source of migration strategy."""
    reference = _reference_policy_yaml(_resolve_reference_dir(raw, project_root))
    if not reference:
        return

    segments = _segment_substitution_contract(reference.get("segment_substitutions"))
    if not segments:
        raise ValueError("reference/symbol_mapping.yaml 必须提供 segment_substitutions")
    raw.setdefault("mapping", {})["segment_substitutions"] = segments

    policy = reference.get("migration_policy")
    if not isinstance(policy, dict):
        raise ValueError("reference/symbol_mapping.yaml 必须提供 migration_policy")
    raw["migration_policy"] = _reference_migration_policy_raw(policy)

    raw.setdefault("dependency_analysis", {})["symbol_dependencies"] = _symbol_dependency_contract(
        reference.get("symbol_dependencies")
    )


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
        _apply_reference_strategy(merged, project_root)

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
        self._validate_reference_consistency()

    def _validate_reference_consistency(self) -> None:
        """Ensure audited reference policy stays aligned with runtime config."""
        reference = _reference_policy_yaml(self.reference_dir)
        if not reference:
            return

        ref_segments = _segment_substitution_contract(reference.get("segment_substitutions"))
        cfg_segments = _segment_substitution_contract(self.raw.get("mapping", {}).get("segment_substitutions"))
        if ref_segments and cfg_segments != ref_segments:
            raise ValueError(
                "mapping.segment_substitutions 与 reference/symbol_mapping.yaml 不一致；"
                "请先更新 reference 这个策略单一事实源。"
            )

        ref_policy_raw = reference.get("migration_policy")
        if isinstance(ref_policy_raw, dict):
            ref_policy = _migration_policy_contract(ref_policy_raw)
            cfg_policy = _migration_policy_contract(self.raw.get("migration_policy"))
            if cfg_policy != ref_policy:
                raise ValueError(
                    "migration_policy 与 reference/symbol_mapping.yaml 不一致；"
                    "请保持 config 与 reference 策略同步。"
                )

        ref_symbol_deps = _symbol_dependency_contract(reference.get("symbol_dependencies"))
        cfg_symbol_deps = _symbol_dependency_contract(
            self.raw.get("dependency_analysis", {}).get("symbol_dependencies")
        )
        if ref_symbol_deps and cfg_symbol_deps != ref_symbol_deps:
            raise ValueError(
                "dependency_analysis.symbol_dependencies 与 reference/symbol_mapping.yaml 不一致；"
                "请保持 reference 这个符号依赖事实源同步。"
            )

    # ----- 便捷访问器 ----- #
    @property
    def output_dir(self) -> Path:
        raw = self.raw["paths"]["output_dir"]
        p = Path(raw)
        return p if p.is_absolute() else (self.project_root / p)

    @property
    def reference_dir(self) -> Path:
        """可审计知识库目录（reference/）。相对路径相对于 PROJECT_ROOT。"""
        raw = self.raw["paths"].get("reference_dir", str(self.project_root / "reference"))
        p = Path(raw)
        return p if p.is_absolute() else (self.project_root / p)

    @property
    def cccl_repo(self) -> str:
        return self.raw["paths"]["cccl_repo"]

    @property
    def symbol_dependency_rules(self) -> list[dict]:
        return copy.deepcopy(self.raw.get("dependency_analysis", {}).get("symbol_dependencies", []))

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
    def kernel_soc_version(self) -> str:
        return str(self.raw.get("tests", {}).get("kernel_soc_version", "Ascend950PR_9599"))

    @property
    def kernel_cannsim_soc_version(self) -> str:
        return str(self.raw.get("tests", {}).get("kernel_cannsim_soc_version", "Ascend950"))

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
        return self.raw["mapping"].get("cccl_test_prefix", "libcudacxx/test/libcudacxx/std")

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
    def model_tools_enabled(self) -> bool:
        """是否允许修复模型调用取证/自检工具（read_repo_file/grep_repo/...）。默认关闭。"""
        return bool(self.raw["model"].get("tools_enabled", False))

    @property
    def model_max_tool_rounds(self) -> int:
        return int(self.raw["model"].get("max_tool_rounds", 4))

    @property
    def draft_samples(self) -> int:
        """初稿/测试迁移的候选采样数（best-of-N）。1=单发（默认，行为不变）。"""
        return max(1, int(self.raw["model"].get("draft_samples", 1)))

    @property
    def examples_retrieval_enabled(self) -> bool:
        """是否按算子相关度从 examples/ 检索 few-shot（默认开）。关掉则用 configured 顺序。"""
        return bool(self.raw.get("few_shot", {}).get("retrieval", True))

    @property
    def few_shot_top_k(self) -> int:
        return max(1, int(self.raw.get("few_shot", {}).get("top_k", 2)))

    @property
    def repo_verify(self) -> dict:
        return self.raw["repo_verify"]

    @property
    def max_fix_rounds(self) -> int:
        return int(self.raw["retry"]["max_fix_rounds"])

    @property
    def normalize_options(self) -> dict:
        return self.raw.get("normalize", {})

    @property
    def migration_policy(self) -> "MigrationPolicy":
        """迁移策略（延期前缀 / bootstrap 覆盖 / 兼容包装 / 公开伞头），单一事实源。"""
        return MigrationPolicy.from_raw(self.raw.get("migration_policy"))

    def skill_path(self, name: str) -> Path:
        return self.project_root / "skills" / name

    def read_skill(self, name: str) -> str:
        """读取 skill 提示词，并展开 ``{{include: _shared/xxx.md}}`` 片段引用。

        把各 fix/migrate 提示词里重复抄写的铁律（算子语义为基准、kernel_spec 槽位契约、
        host 测试必返回非零）收敛到 skills/_shared/ 单一事实源，避免多份漂移。
        """
        return self._expand_skill_includes(self.skill_path(name), set())

    def _expand_skill_includes(self, path: Path, seen: set) -> str:
        resolved = path.resolve()
        if resolved in seen:
            raise ValueError(f"skill include 循环引用: {path}")
        seen = seen | {resolved}
        text = path.read_text(encoding="utf-8")

        def repl(match: "re.Match") -> str:
            inc_name = match.group(1).strip()
            inc_path = self.project_root / "skills" / inc_name
            return self._expand_skill_includes(inc_path, seen).rstrip("\n")

        return re.sub(
            r"^\{\{\s*include:\s*(.+?)\s*\}\}[ \t]*$",
            repl,
            text,
            flags=re.MULTILINE,
        )

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
