"""Generate and run host/kernel tests for converted operators."""

from __future__ import annotations

import re
import shlex
import shutil
import stat
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

from core.config import Config
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
    commands: list[str] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


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
    ):
        self.config = config
        self.verbose = verbose
        self.dry_run = dry_run

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
                "    // Auto-generated smoke test.\n"
                "    // If this operator needs different signature/types, edit this file.\n"
                f"    auto out = ascend::std::{algo}(1.0f, 2.0f);\n"
                "    (void)out;\n"
                "    return 0;\n"
                "}\n"
            )
        return f'#include "{include_path}"\n#include <cassert>\n\n{body}'

    @staticmethod
    def _kernel_host_h(algo: str) -> str:
        guard = f"LIBASCENDCXX_TEST_LIBASCENDCXX_ASCEND_KERNEL_{algo.upper()}_EXAMPLE_HOST_H_"
        return (
            f"#ifndef {guard}\n"
            f"#define {guard}\n\n"
            "#include <cstdint>\n\n"
            f"void ascend_std_{algo}_do(uint32_t core_num, void* stream, uint8_t* x_dev, uint8_t* y_dev, uint8_t* z_dev);\n\n"
            f"#endif  // {guard}\n"
        )

    @staticmethod
    def _kernel_host_cpp(algo: str) -> str:
        return (
            '#include "host.h"\n\n'
            f'extern "C" void aclrtlaunch_{algo}_kernel(uint32_t core_num, void* stream, void* x, void* y, void* z);\n\n'
            f"void ascend_std_{algo}_do(uint32_t core_num, void* stream, uint8_t* x_dev, uint8_t* y_dev, uint8_t* z_dev)\n"
            "{\n"
            f"    aclrtlaunch_{algo}_kernel(core_num, stream, x_dev, y_dev, z_dev);\n"
            "}\n"
        )

    # kernel 仿真 workload 档位。fast：1 核 × 1 tile × 64 = 64 元素，camodel
    # 数十秒可完成（CI/冒烟）；full：8 核 × 32 tile × 64 = 16384 元素（最终验证，
    # 与 mylearn 同量级）。文件里写入 `auto-workload=<tag>` 标记，便于切档时识别重生成。
    @staticmethod
    def _kernel_workload(fast: bool) -> dict:
        if fast:
            return {"tag": "fast", "core_num": 1, "tile_num": 1, "tile_size": 64}
        return {"tag": "full", "core_num": 8, "tile_num": 32, "tile_size": 64}

    @classmethod
    def _kernel_cpp(cls, algo: str, include_path: str, fast: bool = False) -> str:
        w = cls._kernel_workload(fast)
        total_length = w["core_num"] * w["tile_num"] * w["tile_size"]
        return (
            f"// auto-workload={w['tag']} (n={total_length}, cores={w['core_num']}, "
            f"tiles={w['tile_num']}x{w['tile_size']})\n"
            '#include "kernel_operator.h"\n'
            f'#include "{include_path}"\n\n'
            f'extern "C" __global__ __aicore__ void {algo}_kernel(GM_ADDR x_gm, GM_ADDR y_gm, GM_ADDR z_gm)\n'
            "{\n"
            f"    constexpr int32_t TOTAL_LENGTH = {total_length};\n"
            f"    constexpr int32_t CORE_NUM = {w['core_num']};\n"
            "    constexpr int32_t BLOCK_LENGTH = TOTAL_LENGTH / CORE_NUM;\n"
            f"    constexpr int32_t TILE_NUM = {w['tile_num']};\n"
            f"    constexpr int32_t TILE_SIZE = {w['tile_size']};\n\n"
            "    uint32_t block_id = AscendC::GetBlockIdx();\n\n"
            "    AscendC::GlobalTensor<float> xGm, yGm, zGm;\n"
            "    xGm.SetGlobalBuffer((__gm__ float*)(x_gm) + block_id * BLOCK_LENGTH, BLOCK_LENGTH);\n"
            "    yGm.SetGlobalBuffer((__gm__ float*)(y_gm) + block_id * BLOCK_LENGTH, BLOCK_LENGTH);\n"
            "    zGm.SetGlobalBuffer((__gm__ float*)(z_gm) + block_id * BLOCK_LENGTH, BLOCK_LENGTH);\n\n"
            "    AscendC::TQue<AscendC::TPosition::VECIN, 1> inQueueX, inQueueY;\n"
            "    AscendC::TQue<AscendC::TPosition::VECOUT, 1> outQueueZ;\n\n"
            "    AscendC::TPipe pipe;\n"
            "    pipe.InitBuffer(inQueueX, 1, TILE_SIZE * sizeof(float));\n"
            "    pipe.InitBuffer(inQueueY, 1, TILE_SIZE * sizeof(float));\n"
            "    pipe.InitBuffer(outQueueZ, 1, TILE_SIZE * sizeof(float));\n\n"
            "    for (int32_t tile = 0; tile < TILE_NUM; ++tile) {\n"
            "        auto xBuf = inQueueX.AllocTensor<float>();\n"
            "        auto yBuf = inQueueY.AllocTensor<float>();\n"
            "        AscendC::DataCopy(xBuf, xGm[tile * TILE_SIZE], TILE_SIZE);\n"
            "        AscendC::DataCopy(yBuf, yGm[tile * TILE_SIZE], TILE_SIZE);\n"
            "        inQueueX.EnQue(xBuf);\n"
            "        inQueueY.EnQue(yBuf);\n\n"
            "        auto xLocal = inQueueX.DeQue<float>();\n"
            "        auto yLocal = inQueueY.DeQue<float>();\n"
            "        auto zLocal = outQueueZ.AllocTensor<float>();\n\n"
            "        for (int32_t i = 0; i < TILE_SIZE; ++i) {\n"
            "            float x_val = xLocal.GetValue(i);\n"
            "            float y_val = yLocal.GetValue(i);\n"
            f"            float z_val = ascend::std::{algo}(x_val, y_val);\n"
            "            zLocal.SetValue(i, z_val);\n"
            "        }\n\n"
            "        outQueueZ.EnQue(zLocal);\n"
            "        inQueueX.FreeTensor(xLocal);\n"
            "        inQueueY.FreeTensor(yLocal);\n\n"
            "        auto zBuf = outQueueZ.DeQue<float>();\n"
            "        AscendC::DataCopy(zGm[tile * TILE_SIZE], zBuf, TILE_SIZE);\n"
            "        outQueueZ.FreeTensor(zBuf);\n"
            "    }\n"
            "}\n"
        )

    @classmethod
    def _kernel_main_cpp(cls, algo: str, include_path: str, fast: bool = False) -> str:
        w = cls._kernel_workload(fast)
        total_length = w["core_num"] * w["tile_num"] * w["tile_size"]
        return (
            f"// auto-workload={w['tag']} (n={total_length}, cores={w['core_num']})\n"
            '#include "acl/acl.h"\n'
            '#include "host.h"\n'
            f'#include "{include_path}"\n'
            "#include <cmath>\n"
            "#include <iostream>\n"
            "#include <vector>\n\n"
            "#define CHECK_ACL(call)                                                                   \\\n"
            "    do {                                                                                  \\\n"
            "        aclError err = call;                                                              \\\n"
            "        if (err != ACL_SUCCESS) {                                                         \\\n"
            '            std::cerr << "ACL error: " << err << " at " << __FILE__ << ":" << __LINE__ \\\n'
            '                      << std::endl;                                                       \\\n'
            "            return 1;                                                                      \\\n"
            "        }                                                                                  \\\n"
            "    } while (0)\n\n"
            "int main()\n"
            "{\n"
            f"    const size_t n = {total_length};\n"
            "    const size_t bytes = n * sizeof(float);\n\n"
            "    CHECK_ACL(aclInit(nullptr));\n"
            "    CHECK_ACL(aclrtSetDevice(0));\n\n"
            "    void* stream = nullptr;\n"
            "    CHECK_ACL(aclrtCreateStream(&stream));\n\n"
            "    std::vector<float> h_x(n), h_y(n), h_z(n);\n"
            "    for (size_t i = 0; i < n; ++i) {\n"
            "        h_x[i] = static_cast<float>(i);\n"
            "        h_y[i] = static_cast<float>(i * 2);\n"
            "    }\n\n"
            "    void *d_x = nullptr, *d_y = nullptr, *d_z = nullptr;\n"
            "    CHECK_ACL(aclrtMalloc(&d_x, bytes, ACL_MEM_MALLOC_HUGE_FIRST));\n"
            "    CHECK_ACL(aclrtMalloc(&d_y, bytes, ACL_MEM_MALLOC_HUGE_FIRST));\n"
            "    CHECK_ACL(aclrtMalloc(&d_z, bytes, ACL_MEM_MALLOC_HUGE_FIRST));\n\n"
            "    CHECK_ACL(aclrtMemcpy(d_x, bytes, h_x.data(), bytes, ACL_MEMCPY_HOST_TO_DEVICE));\n"
            "    CHECK_ACL(aclrtMemcpy(d_y, bytes, h_y.data(), bytes, ACL_MEMCPY_HOST_TO_DEVICE));\n\n"
            f"    ascend_std_{algo}_do({w['core_num']}, stream, static_cast<uint8_t*>(d_x), static_cast<uint8_t*>(d_y), static_cast<uint8_t*>(d_z));\n"
            "    CHECK_ACL(aclrtSynchronizeStream(stream));\n"
            "    CHECK_ACL(aclrtMemcpy(h_z.data(), bytes, d_z, bytes, ACL_MEMCPY_DEVICE_TO_HOST));\n\n"
            "    constexpr float eps = 1e-5f;\n"
            "    for (size_t i = 0; i < n; ++i) {\n"
            f"        float expected = ascend::std::{algo}(h_x[i], h_y[i]);\n"
            "        if (std::abs(h_z[i] - expected) > eps) {\n"
            '            std::cerr << "Mismatch at i=" << i << ", got=" << h_z[i]\n'
            '                      << ", expected=" << expected << std::endl;\n'
            "            return 2;\n"
            "        }\n"
            "    }\n\n"
            "    aclrtFree(d_x);\n"
            "    aclrtFree(d_y);\n"
            "    aclrtFree(d_z);\n"
            "    aclrtDestroyStream(stream);\n"
            "    aclrtResetDevice(0);\n"
            "    aclFinalize();\n\n"
            '    std::cout << "kernel simulation verification passed." << std::endl;\n'
            "    return 0;\n"
            "}\n"
        )

    # cannsim `-s Ascend950` 对应的 SOC_VERSION 变体。
    # mylearn(alpha.1)叫 Ascend910_9599；新版 CANN(9.0.0 master)把同一颗 9599
    # 芯片改名为 Ascend950PR_9599——cmake 会 TOLOWER 后比对支持列表，旧名已不在表里。
    # 换 toolkit 时只需改这一处（host_config.cmake 的支持列表决定可选值）。
    KERNEL_SOC_VERSION = "Ascend950PR_9599"

    @classmethod
    def _kernel_cmakelists(cls) -> str:
        return (
            "cmake_minimum_required(VERSION 3.16)\n"
            "project(Ascend_c)\n\n"
            f'set(SOC_VERSION "{cls.KERNEL_SOC_VERSION}" CACHE STRING "system on chip type")\n'
            "set(ASCEND_CANN_PACKAGE_PATH $ENV{ASCEND_HOME_PATH}\n"
            '    CACHE STRING "ASCEND CANN package installation directory"\n'
            ")\n"
            "if(NOT CMAKE_BUILD_TYPE)\n"
            '    set(CMAKE_BUILD_TYPE "Debug" CACHE STRING "Build type Release/Debug (default Debug)" FORCE)\n'
            "endif()\n\n"
            "file(GLOB KERNEL_FILES ${CMAKE_CURRENT_SOURCE_DIR}/kernel.cpp)\n\n"
            "include(cmake/npu_lib.cmake)\n"
            "add_executable(ascendc_kernels_bbit ${CMAKE_CURRENT_SOURCE_DIR}/main.cpp ${CMAKE_CURRENT_SOURCE_DIR}/host.cpp)\n\n"
            "target_compile_options(ascendc_kernels_bbit PRIVATE\n"
            "    -O2 -std=c++17 -D_GLIBCXX_USE_CXX11_ABI=0 -Wall -Werror\n"
            ")\n"
            "target_link_libraries(ascendc_kernels_bbit PRIVATE\n"
            "    host_intf_pub\n"
            "    ascendc_kernels_npu\n"
            ")\n"
            "install(TARGETS ascendc_kernels_bbit\n"
            "    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}\n"
            "    ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}\n"
            "    RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}\n"
            ")\n"
        )

    # 与 mylearn 的 max_example/run_test.sh 一致：先准备 CANN 环境，再
    # 对每一步（cmake/make/cannsim）做显式失败检查，任何一步失败立即 exit 1。
    # 末尾仅在全部成功时才打印 PASS 标记（KERNEL_SIM_RESULT: PASS）。
    KERNEL_PASS_MARKER = "KERNEL_SIM_RESULT: PASS"

    @classmethod
    def _kernel_run_test_sh(cls, algo: str) -> str:
        return (
            "#!/bin/bash\n"
            f"# Kernel simulation test for {algo}.\n"
            "# 保持与 mylearn max_example/run_test.sh 一致的环境与失败处理。\n\n"
            "# --- Ascend / CANN 环境（与 mylearn 一致）---\n"
            'if [ -z "$ASCEND_HOME_PATH" ]; then\n'
            '    if [ -f "/usr/local/Ascend/cann/set_env.sh" ]; then\n'
            "        source /usr/local/Ascend/cann/set_env.sh\n"
            '    elif [ -f "/usr/local/Ascend/ascend-toolkit/set_env.sh" ]; then\n'
            "        source /usr/local/Ascend/ascend-toolkit/set_env.sh\n"
            "    fi\n"
            "fi\n"
            'if [ -d "/usr/local/Ascend/cann/x86_64-linux/lib64" ]; then\n'
            '    export LD_LIBRARY_PATH="/usr/local/Ascend/cann/x86_64-linux/lib64:$LD_LIBRARY_PATH"\n'
            "fi\n\n"
            "set -e  # Exit on any error\n\n"
            'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
            'PROJECT_ROOT="$SCRIPT_DIR/../../../../.."\n'
            'SRC_INCLUDE_DIR="$PROJECT_ROOT/include/ascend"\n'
            'DST_KERNEL_SYMLINK="$SCRIPT_DIR/ascend"\n\n'
            'if [ ! -d "$SRC_INCLUDE_DIR" ]; then\n'
            '    echo "ERROR: source header dir not found: $SRC_INCLUDE_DIR"\n'
            "    exit 1\n"
            "fi\n\n"
            'ln -sfn "$SRC_INCLUDE_DIR" "$DST_KERNEL_SYMLINK"\n'
            'rm -rf "$SCRIPT_DIR/build"\n'
            'mkdir -p "$SCRIPT_DIR/build"\n'
            'cd "$SCRIPT_DIR/build"\n'
            'export CPLUS_INCLUDE_PATH="$SCRIPT_DIR:$CPLUS_INCLUDE_PATH"\n\n'
            'cmake .. || { echo "ERROR: CMake configure failed"; rm -f "$DST_KERNEL_SYMLINK"; exit 1; }\n'
            'make -j"$(nproc)" || { echo "ERROR: build failed"; rm -f "$DST_KERNEL_SYMLINK"; exit 1; }\n\n'
            'rm -f "$DST_KERNEL_SYMLINK"\n'
            'export LD_LIBRARY_PATH="$PWD/lib:$LD_LIBRARY_PATH"\n\n'
            "if ! command -v cannsim &> /dev/null; then\n"
            '    echo "ERROR: cannsim command not found. Please install/enable the CANN simulator."\n'
            "    exit 1\n"
            "fi\n\n"
            "cannsim record ./ascendc_kernels_bbit -s Ascend950 --gen-report \\\n"
            '    || { echo "ERROR: cannsim simulation failed"; exit 1; }\n\n'
            f'echo "kernel simulation for {algo} finished."\n'
            f'echo "{cls.KERNEL_PASS_MARKER}"\n'
        )

    def _copy_kernel_cmake_template(self, kernel_dir: Path) -> None:
        src = self._kernel_root / "max_example" / "cmake"
        dst = kernel_dir / "cmake"
        if dst.exists():
            return
        if not src.exists():
            raise FileNotFoundError(f"缺少 kernel cmake 模板目录: {src}")
        shutil.copytree(src, dst)

    def prepare_tests(self, target_relpath: str, overwrite: bool = False) -> OperatorTestResult:
        result = OperatorTestResult(target_relpath=target_relpath)
        result.algo_name = self.algo_name_from_target_relpath(target_relpath)
        result.include_path = self.include_path_from_target_relpath(target_relpath)

        self._host_dir.mkdir(parents=True, exist_ok=True)
        self._kernel_root.mkdir(parents=True, exist_ok=True)

        host_file = self._host_dir / f"{result.algo_name}_tests.cpp"
        kernel_dir = self._kernel_root / f"{result.algo_name}_example"
        kernel_dir.mkdir(parents=True, exist_ok=True)

        self._write_if_needed(
            host_file,
            self._host_test_code(result.algo_name, result.include_path),
            overwrite=overwrite,
        )
        result.host_prepared = True
        result.host_test_file = str(host_file)

        self._copy_kernel_cmake_template(kernel_dir)
        self._write_if_needed(kernel_dir / "CMakeLists.txt", self._kernel_cmakelists(), overwrite=overwrite)
        self._write_if_needed(kernel_dir / "host.h", self._kernel_host_h(result.algo_name), overwrite=overwrite)
        self._write_if_needed(kernel_dir / "host.cpp", self._kernel_host_cpp(result.algo_name), overwrite=overwrite)
        fast = self._fast_kernel
        tag = self._kernel_workload(fast)["tag"]
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
        self._write_if_needed(run_sh, self._kernel_run_test_sh(result.algo_name), overwrite=overwrite)
        # 无条件规整为 LF：哪怕脚本是旧的 CRLF 文件且本次未重写，也要修好，
        # 否则 bash 下 `set -e` 失效会导致假阳性（见 outputs/kernel_test_*.log）。
        self._normalize_sh_to_lf(run_sh)
        try:
            current_mode = run_sh.stat().st_mode
            run_sh.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except OSError:
            pass

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
        self, script: str, cwd: Path, timeout: int | None = None
    ) -> subprocess.CompletedProcess | None:
        if self.dry_run:
            return None
        try:
            return subprocess.run(
                ["bash", "-lc", script],
                capture_output=True,
                text=True,
                cwd=str(cwd),
                timeout=timeout,
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
    ) -> tuple[bool, str]:
        shown = f"(cd {cwd} && bash -lc {shlex.quote(cmd)})"
        result.commands.append(shown)
        if self.dry_run:
            save_text(log_path, "[dry-run] command not executed.\n" + shown + "\n")
            return False, str(log_path)

        try:
            done = self._run_bash(cmd, cwd=cwd, timeout=timeout)
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
        """run_test 模式的真实判定：退出码为 0 + 命中 PASS 标记 + 无失败特征。"""
        if not returncode_ok:
            return False
        try:
            text = Path(log_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return False
        if cls.KERNEL_PASS_MARKER not in text:
            return False
        return not any(sig in text for sig in cls._KERNEL_FAILURE_SIGNATURES)

    def run_host_test(self, result: OperatorTestResult) -> None:
        pattern = "host\\." + result.algo_name + "$"
        cmd = (
            "set -e\n"
            "source ./000_set_env.sh\n"
            "bash ./001_setup_build.sh\n"
            "cd ./build\n"
            f"make {shlex.quote(result.algo_name + '_host_test')}\n"
            f"ctest -R {shlex.quote(pattern)} -V\n"
        )
        passed, log = self._exec_and_log(
            result,
            cmd=cmd,
            cwd=self._libascendcxx,
            log_path=self._outputs / f"host_test_{result.algo_name}.log",
            timeout=self._host_timeout,
        )
        result.host_ran = not self.dry_run
        result.host_passed = passed
        result.host_log_path = log

    def run_kernel_test(self, result: OperatorTestResult, kernel_mode: str = "run_test") -> None:
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
            )
            # 关键修复：不只看退出码，必须命中真正的 PASS 标记且无失败特征，
            # 否则脚本末尾那句无条件 echo 会把失败误报成通过。
            if not self.dry_run:
                passed = self._kernel_run_test_passed(passed, log)
        elif kernel_mode == "full_project":
            pattern = "kernel\\." + result.algo_name + "\\.sim$"
            cmd = (
                "set -e\n"
                "source ./000_set_env.sh\n"
                "bash ./004_build_cmake_test_host_cannsim.sh\n"
                "cd ./build\n"
                f"ctest -R {shlex.quote(pattern)} -V\n"
            )
            passed, log = self._exec_and_log(
                result,
                cmd=cmd,
                cwd=self._libascendcxx,
                log_path=self._outputs / f"kernel_test_{result.algo_name}.log",
                timeout=self._kernel_timeout,
            )
        else:
            raise ValueError(f"未知 kernel_mode: {kernel_mode}")

        result.kernel_ran = not self.dry_run
        result.kernel_passed = passed
        result.kernel_log_path = log

    def prepare_and_run(
        self,
        target_relpath: str,
        *,
        run_host: bool = True,
        run_kernel: bool = True,
        kernel_mode: str = "run_test",
        prepare_only: bool = False,
        overwrite: bool = False,
    ) -> OperatorTestResult:
        try:
            result = self.prepare_tests(target_relpath, overwrite=overwrite)

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
