"""算子测试迁移：让大模型把 CCCL 侧测试翻译成 ACCL 侧测试。

与 core/fix_once.py 同风格：通过注入的 model_client 调模型，便于 mock 下测试。

产出（MigratedTests）：
    * host_test_code —— 完整的 ascend/host/<algo>_tests.cpp，逐条打印用例数值；
    * kernel_spec    —— kernel 仿真测试的“算子相关槽位”（input_init / element_op_code /
      golden_code / gm_inputs）。其余 AscendC 设备流水线与 ACL/cannsim 由固定脚手架提供。

设计要点：
    * golden_code 必须是**独立**参考实现，绝不调用 ascend::std::<algo>，从而消除
      “期望值与被测函数同源”的自洽假绿。
    * 算子语义以 CCCL/ACCL 头为基准；测试适配算子真实形态（二元返回值 / 原地 void /
      三参等），不得为凑模板而篡改算子签名。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from core.config import Config
from core.model_client import BaseModelClient, extract_json_object
from core.operator_kernel_scaffold import KernelScaffoldBuilder
from core.utils import call_model_with_io, read_text_file, save_text

# kernel_spec 必填槽位。gm_inputs/gm_outputs 控制脚手架生成多少个 GM 输入/输出；
# 旧 spec 未提供 gm_outputs 时等价于单输出。
_KERNEL_SPEC_REQUIRED = ("input_init", "element_op_code", "golden_code")
_MAX_GM_INPUTS = 8
_MAX_GM_OUTPUTS = 8

_HOST_NONZERO_LITERAL_RETURN_RE = re.compile(r"\breturn\s+(?:[1-9]\d*|EXIT_FAILURE)\s*;")
_HOST_FAILURE_STATUS_RETURN_RE = re.compile(
    r"\breturn\s+[^;]*(?:fail|error|status)[^;]*;",
    flags=re.IGNORECASE,
)
_HOST_SUCCESS_TERNARY_RETURN_RE = re.compile(
    r"\breturn\s+[^;]*(?:ok|passed)[^;]*\?\s*0\s*:\s*(?:[1-9]\d*|EXIT_FAILURE)\s*;",
    flags=re.IGNORECASE,
)


@dataclass
class MigratedTests:
    algo_name: str
    host_test_code: str = ""
    kernel_spec: dict = field(default_factory=dict)
    notes: str = ""

    def has_host(self) -> bool:
        return bool(self.host_test_code.strip())

    def has_kernel(self) -> bool:
        return bool(self.kernel_spec) and all(
            str(self.kernel_spec.get(k, "")).strip() for k in _KERNEL_SPEC_REQUIRED
        )


def _normalize_count(value, *, default: int, minimum: int, maximum: int) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError):
        return default
    if count < minimum or count > maximum:
        return default
    return count


def validate_kernel_spec(spec: dict) -> dict:
    """校验/规整 kernel_spec：确保必填槽位存在且为字符串，IO 数量在脚手架范围内。"""
    if not isinstance(spec, dict):
        raise ValueError(f"kernel_spec 必须是对象，实际为: {type(spec).__name__}")
    missing = [k for k in _KERNEL_SPEC_REQUIRED if not str(spec.get(k, "")).strip()]
    if missing:
        raise ValueError(f"kernel_spec 缺少必填槽位: {missing}")
    out = {k: str(spec[k]) for k in _KERNEL_SPEC_REQUIRED}
    out["gm_inputs"] = _normalize_count(
        spec.get("gm_inputs", 2), default=2, minimum=1, maximum=_MAX_GM_INPUTS
    )
    out["gm_outputs"] = _normalize_count(
        spec.get("gm_outputs", 1), default=1, minimum=1, maximum=_MAX_GM_OUTPUTS
    )
    # dtype 可选：仅在模型显式给出时透传，并经脚手架白名单规整（未知类型回退 float）。
    if str(spec.get("dtype", "")).strip():
        out["dtype"] = KernelScaffoldBuilder.dtype(spec)
    return out


def validate_host_test_code(code: object) -> str:
    """校验模型生成的 host 测试。

    host 测试是语义验收的主入口，不能只打印 FAIL 后仍然 return 0。这里做轻量
    静态校验：测试可以用 assert 直接中止，也可以显式 return 1/EXIT_FAILURE，
    或基于 failures/ok/status 等状态表达式返回非零。
    """
    if not isinstance(code, str) or not code.strip():
        raise ValueError("模型输出缺少 host_test_code")
    text = code.strip()
    if (
        re.search(r"\bassert\s*\(", text)
        or _HOST_NONZERO_LITERAL_RETURN_RE.search(text)
        or _HOST_FAILURE_STATUS_RETURN_RE.search(text)
        or _HOST_SUCCESS_TERNARY_RETURN_RE.search(text)
    ):
        return text + "\n" if not text.endswith("\n") else text
    raise ValueError("host_test_code 必须在任一用例失败时返回非零，不能只打印 FAIL 后 return 0")


def _read_optional(path_str: str) -> str:
    try:
        return read_text_file(path_str)
    except FileNotFoundError:
        return ""


def _build_examples_block(config: Config) -> str:
    blocks: list[str] = []
    for key, ex in config.test_example_paths().items():
        cccl_test = _read_optional(ex.get("cccl_test", ""))
        accl_host = _read_optional(ex.get("accl_host", ""))
        accl_kernel_spec = _read_optional(ex.get("accl_kernel_spec", ""))
        if not (cccl_test and accl_host and accl_kernel_spec):
            continue
        blocks.append(
            f"""====================
【测试迁移示例 {key} —— CCCL 侧测试】
{cccl_test}

【测试迁移示例 {key} —— 正确的 ACCL host 测试】
{accl_host}

【测试迁移示例 {key} —— 正确的 ACCL kernel_spec(JSON)】
{accl_kernel_spec}
"""
        )
    return "\n".join(blocks)


def build_test_migration_request(
    *,
    algo_name: str,
    include_path: str,
    target_relpath: str,
    cccl_header_text: str,
    accl_header_text: str,
    cccl_test_text: str,
    examples_block: str,
) -> str:
    return f"""【algo_name】
{algo_name}

【include_path（host/kernel 测试里 include 的路径）】
{include_path}

【target_relpath（ACCL 头在仓库中的相对路径）】
{target_relpath}

【CCCL 头文件内容（语义参考）】
{cccl_header_text}

【已迁移好的 ACCL 头文件内容（真实可调用签名，以此为准）】
{accl_header_text}

【CCCL 侧测试代码（要迁移的用例来源）】
{cccl_test_text}

{examples_block}
"""


def migrate_operator_tests(
    config: Config,
    model_client: BaseModelClient,
    *,
    algo_name: str,
    include_path: str,
    target_relpath: str,
    cccl_header_text: str,
    accl_header_text: str,
    cccl_test_text: str,
    prompt_filename: str = "migrate_tests.md",
    verbose: bool = True,
    show_model_io: bool = False,
) -> MigratedTests:
    """调模型，把 CCCL 测试迁移为 ACCL host 测试 + kernel_spec。"""
    out = config.output_dir
    examples_block = _build_examples_block(config)
    request_text = build_test_migration_request(
        algo_name=algo_name,
        include_path=include_path,
        target_relpath=target_relpath,
        cccl_header_text=cccl_header_text,
        accl_header_text=accl_header_text,
        cccl_test_text=cccl_test_text,
        examples_block=examples_block,
    )
    save_text(out / "test_migrate_request.md", request_text)

    prompt_text = config.read_skill(prompt_filename)
    if verbose:
        print(f"开始调用模型迁移 {algo_name} 的测试代码...")
    raw = call_model_with_io(
        model_client,
        stage=f"测试迁移（{algo_name}）",
        system_prompt=prompt_text,
        user_content=request_text,
        show_io=show_model_io,
    )
    save_text(out / "test_migrate_raw.md", raw)

    data = extract_json_object(raw)
    host_test_code = validate_host_test_code(data.get("host_test_code", ""))
    kernel_spec = validate_kernel_spec(data.get("kernel_spec", {}))
    notes = str(data.get("notes", "")).strip()

    result = {
        "host_test_code": host_test_code.rstrip("\n"),
        "kernel_spec": kernel_spec,
        "notes": notes,
    }
    save_text(out / "test_migrate_result.json", json.dumps(result, ensure_ascii=False, indent=2))
    return MigratedTests(
        algo_name=algo_name,
        host_test_code=host_test_code,
        kernel_spec=kernel_spec,
        notes=notes,
    )
