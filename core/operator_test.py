"""Generate and run host/kernel tests for converted operators."""

from __future__ import annotations

import json
import os
import re
import shlex
import stat
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

from core.config import Config
from core import build_env, scaffold_scripts
from core.failure_triage import classify_failure
from core.operator_kernel_scaffold import (
    KERNEL_PASS_MARKER,
    KERNEL_SOC_VERSION,
    KERNEL_VERIFY_MARKER,
    KernelScaffoldBuilder,
)
from core.utils import save_text


@dataclass
class OperatorTestResult:
    target_relpath: str
    algo_name: str = ""
    include_path: str = ""
    host_test_file: str = ""
    kernel_test_dir: str = ""
    host_prepared: bool = False
    kernel_prepared: bool = False
    host_ran: bool = False
    kernel_ran: bool = False
    host_passed: bool = False
    kernel_passed: bool = False
    host_log_path: str = ""
    kernel_log_path: str = ""
    # 失败分类：env（环境问题，改代码无用）/ code（模型可修）/ unknown / skipped。
    host_failure_kind: str = ""
    kernel_failure_kind: str = ""
    host_skipped_reason: str = ""
    kernel_skipped_reason: str = ""
    commands: list[str] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def env_blocked(self) -> bool:
        """是否存在「环境类」失败（应修环境/跳过，而不是回传模型改代码）。"""
        return "env" in (self.host_failure_kind, self.kernel_failure_kind)


class OperatorTestRunner:
    """运行已整合进本项目的 ACCL host/kernel 测试链路（原 mylearn 的两侧测试）。"""

    def __init__(
        self,
        config: Config,
        verbose: bool = True,
        dry_run: bool = False,
        *,
        kernel_timeout_sec: int | None = None,
        host_timeout_sec: int | None = None,
        fast_kernel: bool | None = None,
        kernel_print_samples: int | None = None,
    ):
        self.config = config
        self.verbose = verbose
        self.dry_run = dry_run
        # kernel 逐元素打印条数（None=用 main.cpp 默认 8；负数=全部）。
        self._kernel_print_samples = kernel_print_samples

        # 超时与快速档：显式参数优先，否则回退到 config（再回退到内置默认）。
        self._kernel_timeout = (
            kernel_timeout_sec if kernel_timeout_sec is not None
            else getattr(config, "kernel_timeout_sec", 1200)
        )
        self._host_timeout = (
            host_timeout_sec if host_timeout_sec is not None
            else getattr(config, "host_timeout_sec", 600)
        )
        self._fast_kernel = (
            fast_kernel if fast_kernel is not None
            else getattr(config, "fast_kernel", False)
        )
        self._kernel_soc_version = getattr(config, "kernel_soc_version", KERNEL_SOC_VERSION)
        self._kernel_cannsim_soc_version = getattr(config, "kernel_cannsim_soc_version", "Ascend950")

        self._target_repo = Path(config.target_repo).resolve()
        self._libascendcxx = self._target_repo / "libascendcxx"
        self._host_dir = self._libascendcxx / "test" / "libascendcxx" / "ascend" / "host"
        self._kernel_root = self._libascendcxx / "test" / "libascendcxx" / "ascend" / "kernel"
        self._outputs = config.output_dir

    def _log(self, *args) -> None:
        if self.verbose:
            print(*args)

    @staticmethod
    def algo_name_from_target_relpath(target_relpath: str) -> str:
        stem = Path(target_relpath).stem
        algo = re.sub(r"[^0-9A-Za-z_]", "_", stem)
        if not algo:
            return "unknown_op"
        if re.match(r"^[0-9]", algo):
            return f"op_{algo}"
        return algo

    @staticmethod
    def include_path_from_target_relpath(target_relpath: str) -> str:
        rel = str(target_relpath).replace("\\", "/").strip("/")
        marker = "/include/"
        if marker in rel:
            return rel.split(marker, 1)[1]
        if rel.startswith("include/"):
            return rel[len("include/") :]
        raise ValueError(f"无法从 target_relpath 推导 include 路径: {target_relpath}")

    @staticmethod
    def _write_if_needed(path: Path, text: str, overwrite: bool) -> None:
        if path.exists() and not overwrite:
            return
        save_text(path, text)

    @staticmethod
    def _write_workload_if_needed(path: Path, text: str, overwrite: bool, tag: str) -> None:
        """与 _write_if_needed 类似，但 fast/full 档位切换时即使未显式 overwrite 也重生成。

        生成的 kernel.cpp/main.cpp 顶部带 `auto-workload=<tag>` 标记：
        - 同档位且文件已存在 → 保留（允许用户手改）；
        - 档位不同（或无标记）→ 用新档位重新生成。
        """
        if path.exists() and not overwrite:
            try:
                on_disk = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                on_disk = ""
            if f"auto-workload={tag}" in on_disk:
                return
        save_text(path, text)

    @staticmethod
    def _normalize_sh_to_lf(path: Path) -> None:
        """把 shell 脚本统一成 LF 换行。

        本项目位于 /mnt/c（Windows 卷），脚本可能被 Windows 编辑器写成 CRLF，
        导致 `set -e` 失效、cmake/make 参数被 `\\r` 污染（kernel_test 日志即此症状）。
        这里无条件修复：即使 run_test.sh 已存在且未被重写，也强制规整为 LF。
        """
        if not path.exists():
            return
        try:
            raw = path.read_bytes()
        except OSError:
            return
        normalized = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        if normalized != raw:
            path.write_bytes(normalized)

    @staticmethod
    def _is_smoke_host_test(path: Path) -> bool:
        """现有 host 测试是否只是 SMOKE 回退占位（含 SMOKE-ONLY 标记）。

        真实测试（模型迁移版、或内置 max/min 带断言版）不含该标记，因此可据此区分：
        SMOKE 占位可被安全刷新，真实测试绝不被回退模板覆盖。
        """
        try:
            return "SMOKE-ONLY" in path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return False

    @staticmethod
    def _host_test_code(algo: str, include_path: str) -> str:
        if algo == "max":
            body = (
                "void test_max_basic()\n"
                "{\n"
                "    assert(ascend::std::max(1, 2) == 2);\n"
                "    assert(ascend::std::max(5.0f, 3.0f) == 5.0f);\n"
                "}\n\n"
                "void test_max_custom_comp()\n"
                "{\n"
                "    auto comp = [](int a, int b) { return a < b; };\n"
                "    assert(ascend::std::max(10, 20, comp) == 20);\n"
                "}\n\n"
                "int main()\n"
                "{\n"
                "    test_max_basic();\n"
                "    test_max_custom_comp();\n"
                "    return 0;\n"
                "}\n"
            )
        elif algo == "min":
            body = (
                "void test_min_basic()\n"
                "{\n"
                "    assert(ascend::std::min(1, 2) == 1);\n"
                "    assert(ascend::std::min(5.0f, 3.0f) == 3.0f);\n"
                "}\n\n"
                "int main()\n"
                "{\n"
                "    test_min_basic();\n"
                "    return 0;\n"
                "}\n"
            )
        else:
            body = (
                "int main()\n"
                "{\n"
                "    // Auto-generated SMOKE test: compile/instantiate only.\n"
                "    // No independent oracle for this operator here, so a pass means it builds\n"
                "    // and the call instantiates, NOT that its semantics are verified.\n"
                "    // Provide a model-migrated host test for real semantic checks.\n"
                f'    std::cout << "[host][{algo}][SMOKE-ONLY] compile/instantiate smoke; '
                'semantic check skipped" << std::endl;\n'
                f"    auto out = ascend::std::{algo}(1.0f, 2.0f);\n"
                "    (void)out;\n"
                "    return 0;\n"
                "}\n"
            )
        return f'#include "{include_path}"\n#include <cassert>\n#include <iostream>\n\n{body}'

    KERNEL_SOC_VERSION = KERNEL_SOC_VERSION
    KERNEL_PASS_MARKER = KERNEL_PASS_MARKER
    KERNEL_VERIFY_MARKER = KERNEL_VERIFY_MARKER

    # 以下若干 _kernel_* 仅是对 KernelScaffoldBuilder 的薄封装，供 prepare_tests 使用，
    # 把"脚手架内容"集中由 KernelScaffoldBuilder 负责，本类只管落盘与执行。
    @staticmethod
    def _kernel_io_shape(kernel_spec: dict | None = None) -> tuple[int, int]:
        return KernelScaffoldBuilder.io_shape(kernel_spec)

    @staticmethod
    def _kernel_host_h(algo: str, gm_inputs: int = 2, gm_outputs: int = 1) -> str:
        return KernelScaffoldBuilder.host_h(algo, gm_inputs, gm_outputs)

    @staticmethod
    def _kernel_host_cpp(algo: str, gm_inputs: int = 2, gm_outputs: int = 1) -> str:
        return KernelScaffoldBuilder.host_cpp(algo, gm_inputs, gm_outputs)

    @staticmethod
    def _kernel_workload(fast: bool) -> dict:
        return KernelScaffoldBuilder.workload(fast)

    @classmethod
    def _kernel_cpp(
        cls, algo: str, include_path: str, fast: bool = False, kernel_spec: dict | None = None
    ) -> str:
        return KernelScaffoldBuilder.kernel_cpp(algo, include_path, fast, kernel_spec)

    @classmethod
    def _kernel_main_cpp(
        cls, algo: str, include_path: str, fast: bool = False, kernel_spec: dict | None = None
    ) -> str:
        return KernelScaffoldBuilder.main_cpp(algo, include_path, fast, kernel_spec)

    def _kernel_cmakelists(self) -> str:
        return KernelScaffoldBuilder.cmakelists(self._kernel_soc_version)

    def _kernel_run_test_sh(self, algo: str) -> str:
        return scaffold_scripts.run_test_sh(algo, self._kernel_cannsim_soc_version)

    @classmethod
    def _host_run_test_sh(cls, algo: str) -> str:
        return scaffold_scripts.host_run_test_sh(algo)

    @classmethod
    def _full_project_run_sh(cls, algo: str) -> str:
        return scaffold_scripts.full_project_run_sh(algo)

    def _write_run_script(self, path: Path, text: str) -> None:
        """落盘生成的运行脚本：强制 LF + 可执行（与 kernel run_test.sh 同处理）。"""
        save_text(path, text)
        self._normalize_sh_to_lf(path)
        try:
            path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except OSError:
            pass

    def _write_kernel_cmake(self, kernel_dir: Path) -> None:
        """生成 `cmake/npu_lib.cmake`（代码即单一事实源）。

        取代旧的「从目标仓 max_example/cmake 拷贝」——那等于把输出当输入，违反
        「输入只在源仓/examples、输出只在目标仓/outputs」。这里与 CMakeLists.txt 一样
        每次刷新，保证 CANN 适配修复对已存在的 *_example 目录也生效。
        """
        save_text(kernel_dir / "cmake" / "npu_lib.cmake", KernelScaffoldBuilder.npu_lib_cmake())

    def prepare_tests(
        self,
        target_relpath: str,
        overwrite: bool = False,
        *,
        host_test_code: str | None = None,
        kernel_spec: dict | None = None,
    ) -> OperatorTestResult:
        """生成 host/kernel 测试脚手架。

        - host_test_code/kernel_spec 由模型迁移产出（core/test_migrator）：
          提供时即写入对应文件（视为最新产物，强制覆盖），算子相关部分不再走写死模板。
        - 都不提供时（离线/mock/legacy）回退到内置二元模板，保持既有行为。
        """
        result = OperatorTestResult(target_relpath=target_relpath)
        result.algo_name = self.algo_name_from_target_relpath(target_relpath)
        result.include_path = self.include_path_from_target_relpath(target_relpath)

        self._host_dir.mkdir(parents=True, exist_ok=True)
        self._kernel_root.mkdir(parents=True, exist_ok=True)

        host_file = self._host_dir / f"{result.algo_name}_tests.cpp"
        kernel_dir = self._kernel_root / f"{result.algo_name}_example"
        kernel_dir.mkdir(parents=True, exist_ok=True)

        if host_test_code and host_test_code.strip():
            # 模型迁移的 host 测试：直接写入（最新产物，覆盖旧文件）。
            save_text(host_file, host_test_code if host_test_code.endswith("\n") else host_test_code + "\n")
        elif not host_file.exists():
            # 首次创建：写内置/回退模板。
            save_text(host_file, self._host_test_code(result.algo_name, result.include_path))
        elif overwrite and self._is_smoke_host_test(host_file):
            # 现有文件本身就是 SMOKE 回退占位，overwrite 时可安全刷新。
            save_text(host_file, self._host_test_code(result.algo_name, result.include_path))
        # 否则保留现有的真实 host 测试：绝不用 SMOKE 占位覆盖已迁移/已手写的真实测试，
        # 即便 overwrite=True（修复"重生成 kernel 时误覆盖 host 测试"的 footgun）。
        result.host_prepared = True
        result.host_test_file = str(host_file)

        self._write_kernel_cmake(kernel_dir)
        # CMakeLists.txt is generated fixed scaffolding; refresh it so CANN linker
        # compatibility fixes take effect in existing *_example directories.
        save_text(kernel_dir / "CMakeLists.txt", self._kernel_cmakelists())
        fast = self._fast_kernel
        tag = self._kernel_workload(fast)["tag"]
        spec = kernel_spec if (kernel_spec and kernel_spec.get("element_op_code")) else None
        gm_inputs, gm_outputs = self._kernel_io_shape(spec)
        if spec is not None:
            # IO shape is part of the migrated kernel contract, so host glue must
            # be regenerated together with kernel.cpp/main.cpp.
            save_text(kernel_dir / "host.h", self._kernel_host_h(result.algo_name, gm_inputs, gm_outputs))
            save_text(kernel_dir / "host.cpp", self._kernel_host_cpp(result.algo_name, gm_inputs, gm_outputs))
        else:
            self._write_if_needed(
                kernel_dir / "host.h",
                self._kernel_host_h(result.algo_name, gm_inputs, gm_outputs),
                overwrite=overwrite,
            )
            self._write_if_needed(
                kernel_dir / "host.cpp",
                self._kernel_host_cpp(result.algo_name, gm_inputs, gm_outputs),
                overwrite=overwrite,
            )
        # 有模型 spec 时强制覆盖 kernel.cpp/main.cpp（最新产物）；否则保留 fast/full 档位逻辑。
        if spec is not None:
            save_text(kernel_dir / "kernel.cpp", self._kernel_cpp(result.algo_name, result.include_path, fast, spec))
            save_text(kernel_dir / "main.cpp", self._kernel_main_cpp(result.algo_name, result.include_path, fast, spec))
            save_text(kernel_dir / "kernel_spec.json", json.dumps(spec, ensure_ascii=False, indent=2))
        else:
            self._write_workload_if_needed(
                kernel_dir / "kernel.cpp",
                self._kernel_cpp(result.algo_name, result.include_path, fast),
                overwrite=overwrite,
                tag=tag,
            )
            self._write_workload_if_needed(
                kernel_dir / "main.cpp",
                self._kernel_main_cpp(result.algo_name, result.include_path, fast),
                overwrite=overwrite,
                tag=tag,
            )
        run_sh = kernel_dir / "run_test.sh"
        # run_test.sh 是生成脚本，必须随统一环境片段刷新。否则工作区已有旧脚本时，
        # 源码里的环境修复不会生效，仍会跳过 set_env.sh 并缺 libascend_hal/devlib。
        self._write_run_script(run_sh, self._kernel_run_test_sh(result.algo_name))

        result.kernel_prepared = True
        result.kernel_test_dir = str(kernel_dir)
        return result

    @staticmethod
    def _as_text(value) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", "replace")
        return value

    def _run_bash(
        self, script: str, cwd: Path, timeout: int | None = None,
        env_extra: dict | None = None,
    ) -> subprocess.CompletedProcess | None:
        if self.dry_run:
            return None
        run_env = {**os.environ, **env_extra} if env_extra else None
        try:
            return subprocess.run(
                ["bash", "-lc", script],
                capture_output=True,
                text=True,
                cwd=str(cwd),
                timeout=timeout,
                env=run_env,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "未找到 bash。请在可用的 Linux/bash 环境下执行测试，或使用 --test-dry-run 仅生成命令。"
            ) from exc

    def _exec_and_log(
        self,
        result: OperatorTestResult,
        cmd: str,
        cwd: Path,
        log_path: Path,
        timeout: int | None = None,
        env_extra: dict | None = None,
    ) -> tuple[bool, str]:
        shown = f"(cd {cwd} && bash -lc {shlex.quote(cmd)})"
        result.commands.append(shown)
        if self.dry_run:
            save_text(log_path, "[dry-run] command not executed.\n" + shown + "\n")
            return False, str(log_path)

        try:
            done = self._run_bash(cmd, cwd=cwd, timeout=timeout, env_extra=env_extra)
        except subprocess.TimeoutExpired as exc:
            # 超时不再当成崩溃：落盘已捕获的部分输出 + 明确标注，按失败处理。
            text = (
                self._as_text(exc.stdout)
                + "\n"
                + self._as_text(exc.stderr)
                + f"\n[TIMEOUT] 命令超过 {timeout}s 仍未结束，已被终止。"
                + "（kernel 仿真较慢，可调大 tests.kernel_timeout_sec 或用 --kernel-fast 快速档。）\n"
            )
            save_text(log_path, text)
            return False, str(log_path)

        text = (done.stdout or "") + "\n" + (done.stderr or "")
        save_text(log_path, text)
        return bool(done and done.returncode == 0), str(log_path)

    # 即使退出码为 0，这些字样也说明脚本其实失败了（典型：CRLF 让 `set -e`
    # 失效后脚本一路跑到结尾的 echo 仍 exit 0，造成假阳性）。
    _KERNEL_FAILURE_SIGNATURES = (
        "command not found",
        "cannsim command not found",
        "CMake configure failed",
        "CMake Error",
        "build failed",
        "Build failed",
        "invalid option",
        "Mismatch at",
        "ACL error",
        "$'\\r'",
        "\r",
    )

    @classmethod
    def _kernel_run_test_passed(cls, returncode_ok: bool, log_path: str) -> bool:
        """run_test 判定：退出码 + PASS + cannsim verification marker + 无失败特征。"""
        if not returncode_ok:
            return False
        try:
            text = Path(log_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return False
        if cls.KERNEL_PASS_MARKER not in text:
            return False
        if cls.KERNEL_VERIFY_MARKER not in text:
            return False
        return not any(sig in text for sig in cls._KERNEL_FAILURE_SIGNATURES)

    @staticmethod
    def _read_log(log_path: str | None) -> str:
        if not log_path:
            return ""
        try:
            return Path(log_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    def run_host_test(self, result: OperatorTestResult) -> None:
        # 执行前主动清理过期的 CMake 缓存（项目改名/移动后的旧缓存会让 cmake 报错）。
        if not self.dry_run and build_env.remove_stale_cmake_cache(self._libascendcxx / "build"):
            self._log(f"[test] 已清理过期 CMake 缓存: {self._libascendcxx / 'build'}")
        # 生成统一的 host 运行脚本（取代签入的 000/001），保证 host 与 kernel 同源。
        script = self._libascendcxx / "run_host_test.sh"
        self._write_run_script(script, self._host_run_test_sh(result.algo_name))
        cmd = "bash ./run_host_test.sh\n"
        passed, log = self._exec_and_log(
            result,
            cmd=cmd,
            cwd=self._libascendcxx,
            log_path=self._outputs / f"host_test_{result.algo_name}.log",
            timeout=self._host_timeout,
            env_extra=self._kernel_env_extra(),
        )
        result.host_ran = not self.dry_run
        result.host_passed = passed
        result.host_log_path = log
        if not passed and not self.dry_run:
            triage = classify_failure(self._read_log(log))
            result.host_failure_kind = triage.kind
            if triage.is_env:
                self._log(f"[test] host 失败判定为环境问题（{triage.reason}），不进模型修复循环。")

    def _kernel_env_extra(self) -> dict | None:
        """组装 kernel 运行所需的额外环境变量。

        - KERNEL_PRINT_SAMPLES：把逐元素打印条数透传给 main.cpp；
        - PATH：若 llvm-objdump 不在 PATH，补上 CANN 的 ccec_compiler/bin，
          否则 kernel 构建的 extract_host_stub.py 会报 FileNotFoundError。
        """
        env: dict = {}
        if self._kernel_print_samples is not None:
            env["KERNEL_PRINT_SAMPLES"] = str(int(self._kernel_print_samples))
        additions = build_env.cann_path_additions()
        if additions:
            env["PATH"] = os.pathsep.join(additions) + os.pathsep + os.environ.get("PATH", "")
        return env or None

    def run_kernel_test(self, result: OperatorTestResult, kernel_mode: str = "run_test") -> None:
        # 预检：cannsim 不可用时 kernel 仿真无从谈起，标 SKIPPED 而非 FAIL
        # （否则会被当成代码失败，徒劳地回传模型）。llvm-objdump 缺失由 _kernel_env_extra
        # 自动补 PATH，这里不再拦。
        if not self.dry_run:
            missing = build_env.missing_kernel_tools()
            if missing:
                reason = f"缺少 kernel 仿真所需工具: {', '.join(missing)}（请安装/启用 CANN 模拟器）"
                self._log(f"[test] 跳过 kernel 测试：{reason}")
                result.kernel_ran = False
                result.kernel_passed = False
                result.kernel_skipped_reason = reason
                result.kernel_failure_kind = "skipped"
                return

        env_extra = self._kernel_env_extra()
        if kernel_mode == "run_test":
            kernel_dir = self._kernel_root / f"{result.algo_name}_example"
            # 执行前再保险一次：把脚本规整为 LF，避免 CRLF 让 `set -e` 失效。
            self._normalize_sh_to_lf(kernel_dir / "run_test.sh")
            cmd = "bash ./run_test.sh\n"
            passed, log = self._exec_and_log(
                result,
                cmd=cmd,
                cwd=kernel_dir,
                log_path=self._outputs / f"kernel_test_{result.algo_name}.log",
                timeout=self._kernel_timeout,
                env_extra=env_extra,
            )
            # 关键修复：不只看退出码，必须命中真正的 PASS 标记且无失败特征，
            # 否则脚本末尾那句无条件 echo 会把失败误报成通过。
            if not self.dry_run:
                passed = self._kernel_run_test_passed(passed, log)
        elif kernel_mode == "full_project":
            # full_project 走 libascendcxx/build；同样先清掉过期 CMake 缓存。
            if not self.dry_run and build_env.remove_stale_cmake_cache(self._libascendcxx / "build"):
                self._log(f"[test] 已清理过期 CMake 缓存: {self._libascendcxx / 'build'}")
            # 生成统一的 full_project 运行脚本（取代签入的 000/004）。
            script = self._libascendcxx / "run_kernel_full.sh"
            self._write_run_script(script, self._full_project_run_sh(result.algo_name))
            cmd = "bash ./run_kernel_full.sh\n"
            passed, log = self._exec_and_log(
                result,
                cmd=cmd,
                cwd=self._libascendcxx,
                log_path=self._outputs / f"kernel_test_{result.algo_name}.log",
                timeout=self._kernel_timeout,
                env_extra=env_extra,
            )
        else:
            raise ValueError(f"未知 kernel_mode: {kernel_mode}")

        result.kernel_ran = not self.dry_run
        result.kernel_passed = passed
        result.kernel_log_path = log
        if not passed and not self.dry_run:
            triage = classify_failure(self._read_log(log))
            result.kernel_failure_kind = triage.kind
            if triage.is_env:
                self._log(f"[test] kernel 失败判定为环境问题（{triage.reason}），不进模型修复循环。")

    def prepare_and_run(
        self,
        target_relpath: str,
        *,
        run_host: bool = True,
        run_kernel: bool = True,
        kernel_mode: str = "run_test",
        prepare_only: bool = False,
        overwrite: bool = False,
        host_test_code: str | None = None,
        kernel_spec: dict | None = None,
    ) -> OperatorTestResult:
        try:
            result = self.prepare_tests(
                target_relpath,
                overwrite=overwrite,
                host_test_code=host_test_code,
                kernel_spec=kernel_spec,
            )

            if prepare_only:
                return result

            if run_host:
                self._log(f"[test] running host test for {result.algo_name} ...")
                self.run_host_test(result)
            if run_kernel:
                self._log(f"[test] running kernel test for {result.algo_name} ({kernel_mode}) ...")
                self.run_kernel_test(result, kernel_mode=kernel_mode)
            return result
        except Exception as exc:
            failed = OperatorTestResult(target_relpath=target_relpath)
            failed.error = f"{type(exc).__name__}: {exc}"
            return failed
