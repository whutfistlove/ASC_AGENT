"""Kernel-side C++ scaffolding for operator tests.

This module owns the generated AscendC/ACL source templates.  The runner in
``core.operator_test`` remains responsible for filesystem preparation and
command execution.
"""

from __future__ import annotations

KERNEL_SOC_VERSION = "Ascend950PR_9599"
KERNEL_CANNSIM_SOC_VERSION = "Ascend950"
KERNEL_PASS_MARKER = "KERNEL_SIM_RESULT: PASS"
# main.cpp 在「独立 golden 全部命中」时打印的标记。run_test.sh 只在 cannsim.log
# 里看到这一行才认定语义通过 —— 这样数值算错(打印 Mismatch / 无此标记)就不会被
# cannsim 录制成功这件事掩盖成假绿（见问题①）。
KERNEL_VERIFY_MARKER = "kernel simulation verification passed."
# 没有 kernel_spec 时的回退只做 build+launch 冒烟，main.cpp 打印这一行；
# run_test.sh 据此输出 SMOKE 结果而非 PASS，避免「拿算子和自己比」的自洽假绿（问题④）。
KERNEL_SMOKE_MARKER = "SMOKE-ONLY"

# kernel 脚手架按逐元素标量处理，支持浮点与有符号整型。默认 float；
# 整型(如 gcd/lcm)用精确相等比较，浮点用 eps 容差（见问题⑤）。
# 值为 True 表示整型。无符号类型会让 (got-expected) 下溢，故不纳入白名单。
_KERNEL_DTYPES = {
    "float": False,
    "double": False,
    "int": True,
    "int32_t": True,
    "int64_t": True,
    "int16_t": True,
}
DEFAULT_KERNEL_DTYPE = "float"


class KernelScaffoldBuilder:
    """Build host glue, kernel source, main source, CMake, and run script."""

    @staticmethod
    def io_shape(kernel_spec: dict | None = None) -> tuple[int, int]:
        """Return (gm_inputs, gm_outputs) for generated kernel scaffolding."""
        if not kernel_spec:
            return 2, 1

        def count(name: str, default: int) -> int:
            try:
                value = int(kernel_spec.get(name, default))
            except (TypeError, ValueError):
                return default
            return value if 1 <= value <= 8 else default

        return count("gm_inputs", 2), count("gm_outputs", 1)

    @classmethod
    def dtype(cls, kernel_spec: dict | None = None) -> str:
        """Return the validated scalar C++ type for the kernel (default float).

        Unknown / unsupported types fall back to ``float`` so the scaffold never
        emits an uncompilable type.
        """
        if kernel_spec:
            cand = str(kernel_spec.get("dtype", "")).strip()
            if cand in _KERNEL_DTYPES:
                return cand
        return DEFAULT_KERNEL_DTYPE

    @staticmethod
    def is_integral(dtype: str) -> bool:
        return _KERNEL_DTYPES.get(dtype, False)

    @staticmethod
    def kernel_arg_decls(gm_inputs: int, gm_outputs: int, typ: str = "GM_ADDR") -> list[str]:
        return (
            [f"{typ} in{i}_gm" for i in range(gm_inputs)]
            + [f"{typ} out{i}_gm" for i in range(gm_outputs)]
        )

    @staticmethod
    def host_arg_decls(gm_inputs: int, gm_outputs: int) -> list[str]:
        return (
            [f"uint8_t* in{i}_dev" for i in range(gm_inputs)]
            + [f"uint8_t* out{i}_dev" for i in range(gm_outputs)]
        )

    @staticmethod
    def launch_arg_decls(gm_inputs: int, gm_outputs: int) -> list[str]:
        return (
            [f"void* in{i}" for i in range(gm_inputs)]
            + [f"void* out{i}" for i in range(gm_outputs)]
        )

    @staticmethod
    def host_launch_args(gm_inputs: int, gm_outputs: int) -> list[str]:
        return (
            [f"in{i}_dev" for i in range(gm_inputs)]
            + [f"out{i}_dev" for i in range(gm_outputs)]
        )

    @classmethod
    def host_h(cls, algo: str, gm_inputs: int = 2, gm_outputs: int = 1) -> str:
        guard = f"LIBASCENDCXX_TEST_LIBASCENDCXX_ASCEND_KERNEL_{algo.upper()}_EXAMPLE_HOST_H_"
        params = ", ".join(
            ["uint32_t core_num", "void* stream"] + cls.host_arg_decls(gm_inputs, gm_outputs)
        )
        return (
            f"#ifndef {guard}\n"
            f"#define {guard}\n\n"
            "#include <cstdint>\n\n"
            f"void ascend_std_{algo}_do({params});\n\n"
            f"#endif  // {guard}\n"
        )

    @classmethod
    def host_cpp(cls, algo: str, gm_inputs: int = 2, gm_outputs: int = 1) -> str:
        launch_decl = ", ".join(
            ["uint32_t core_num", "void* stream"] + cls.launch_arg_decls(gm_inputs, gm_outputs)
        )
        do_decl = ", ".join(
            ["uint32_t core_num", "void* stream"] + cls.host_arg_decls(gm_inputs, gm_outputs)
        )
        launch_args = ", ".join(["core_num", "stream"] + cls.host_launch_args(gm_inputs, gm_outputs))
        return (
            '#include "host.h"\n\n'
            f'extern "C" void aclrtlaunch_{algo}_kernel({launch_decl});\n\n'
            f"void ascend_std_{algo}_do({do_decl})\n"
            "{\n"
            f"    aclrtlaunch_{algo}_kernel({launch_args});\n"
            "}\n"
        )

    @staticmethod
    def workload(fast: bool) -> dict:
        if fast:
            return {"tag": "fast", "core_num": 1, "tile_num": 1, "tile_size": 64}
        return {"tag": "full", "core_num": 8, "tile_num": 32, "tile_size": 64}

    @classmethod
    def kernel_cpp(
        cls, algo: str, include_path: str, fast: bool = False, kernel_spec: dict | None = None
    ) -> str:
        w = cls.workload(fast)
        total_length = w["core_num"] * w["tile_num"] * w["tile_size"]
        gm_inputs, gm_outputs = cls.io_shape(kernel_spec)
        t = cls.dtype(kernel_spec)
        zero = f"({t})0"
        element_op = (
            str(kernel_spec.get("element_op_code")).strip()
            if kernel_spec and kernel_spec.get("element_op_code")
            else f"z_val = ascend::std::{algo}(x_val, y_val);"
        )
        arg_decls = ", ".join(cls.kernel_arg_decls(gm_inputs, gm_outputs))
        gm_decls = "\n".join(
            [f"    AscendC::GlobalTensor<{t}> in{i}Gm;" for i in range(gm_inputs)]
            + [f"    AscendC::GlobalTensor<{t}> out{i}Gm;" for i in range(gm_outputs)]
        )
        gm_buffers = "\n".join(
            [
                f"    in{i}Gm.SetGlobalBuffer((__gm__ {t}*)(in{i}_gm) + block_id * BLOCK_LENGTH, BLOCK_LENGTH);"
                for i in range(gm_inputs)
            ]
            + [
                f"    out{i}Gm.SetGlobalBuffer((__gm__ {t}*)(out{i}_gm) + block_id * BLOCK_LENGTH, BLOCK_LENGTH);"
                for i in range(gm_outputs)
            ]
        )
        queue_decls = "\n".join(
            [f"    AscendC::TQue<AscendC::TPosition::VECIN, 1> inQueue{i};" for i in range(gm_inputs)]
            + [f"    AscendC::TQue<AscendC::TPosition::VECOUT, 1> outQueue{i};" for i in range(gm_outputs)]
        )
        init_buffers = "\n".join(
            [f"    pipe.InitBuffer(inQueue{i}, 1, TILE_SIZE * sizeof({t}));" for i in range(gm_inputs)]
            + [f"    pipe.InitBuffer(outQueue{i}, 1, TILE_SIZE * sizeof({t}));" for i in range(gm_outputs)]
        )
        alloc_copy_inputs = "\n".join(
            [
                f"        auto in{i}Buf = inQueue{i}.AllocTensor<{t}>();\n"
                f"        AscendC::DataCopy(in{i}Buf, in{i}Gm[tile * TILE_SIZE], TILE_SIZE);\n"
                f"        inQueue{i}.EnQue(in{i}Buf);"
                for i in range(gm_inputs)
            ]
        )
        deque_inputs = "\n".join(
            [f"        auto in{i}Local = inQueue{i}.DeQue<{t}>();" for i in range(gm_inputs)]
        )
        alloc_outputs = "\n".join(
            [f"        auto out{i}Local = outQueue{i}.AllocTensor<{t}>();" for i in range(gm_outputs)]
        )
        value_loads = "\n".join(
            [f"            {t} in{i}_val = in{i}Local.GetValue(i);" for i in range(gm_inputs)]
        )
        legacy_input_aliases = (
            f"            {t} x_val = in0_val;\n"
            + (f"            {t} y_val = in1_val;\n" if gm_inputs >= 2 else f"            {t} y_val = {zero};\n")
            + "            (void)x_val;\n"
            + "            (void)y_val;\n"
            + "".join([f"            (void)in{i}_val;\n" for i in range(gm_inputs)])
        )
        output_values = "\n".join(
            [f"            {t} out{i}_val = {zero};" for i in range(gm_outputs)]
            + [f"            {t}& z_val = out0_val;", "            (void)z_val;"]
            + [f"            (void)out{i}_val;" for i in range(gm_outputs)]
        )
        output_stores = "\n".join(
            [f"            out{i}Local.SetValue(i, out{i}_val);" for i in range(gm_outputs)]
        )
        enqueue_outputs = "\n".join([f"        outQueue{i}.EnQue(out{i}Local);" for i in range(gm_outputs)])
        free_inputs = "\n".join([f"        inQueue{i}.FreeTensor(in{i}Local);" for i in range(gm_inputs)])
        copy_outputs = "\n".join(
            [
                f"        auto out{i}Buf = outQueue{i}.DeQue<{t}>();\n"
                f"        AscendC::DataCopy(out{i}Gm[tile * TILE_SIZE], out{i}Buf, TILE_SIZE);\n"
                f"        outQueue{i}.FreeTensor(out{i}Buf);"
                for i in range(gm_outputs)
            ]
        )
        return (
            f"// auto-workload={w['tag']} (n={total_length}, cores={w['core_num']}, "
            f"tiles={w['tile_num']}x{w['tile_size']}, inputs={gm_inputs}, outputs={gm_outputs}, dtype={t})\n"
            '#include "kernel_operator.h"\n'
            f'#include "{include_path}"\n\n'
            f'extern "C" __global__ __aicore__ void {algo}_kernel({arg_decls})\n'
            "{\n"
            f"    constexpr int32_t TOTAL_LENGTH = {total_length};\n"
            f"    constexpr int32_t CORE_NUM = {w['core_num']};\n"
            "    constexpr int32_t BLOCK_LENGTH = TOTAL_LENGTH / CORE_NUM;\n"
            f"    constexpr int32_t TILE_NUM = {w['tile_num']};\n"
            f"    constexpr int32_t TILE_SIZE = {w['tile_size']};\n\n"
            "    uint32_t block_id = AscendC::GetBlockIdx();\n\n"
            f"{gm_decls}\n"
            f"{gm_buffers}\n\n"
            f"{queue_decls}\n\n"
            "    AscendC::TPipe pipe;\n"
            f"{init_buffers}\n\n"
            "    for (int32_t tile = 0; tile < TILE_NUM; ++tile) {\n"
            f"{alloc_copy_inputs}\n\n"
            f"{deque_inputs}\n"
            f"{alloc_outputs}\n\n"
            "        for (int32_t i = 0; i < TILE_SIZE; ++i) {\n"
            f"{value_loads}\n"
            f"{legacy_input_aliases}"
            f"{output_values}\n"
            f"            {{ {element_op} }}\n"
            f"{output_stores}\n"
            "        }\n\n"
            f"{enqueue_outputs}\n"
            f"{free_inputs}\n\n"
            f"{copy_outputs}\n"
            "    }\n"
            "}\n"
        )

    @classmethod
    def main_cpp(
        cls, algo: str, include_path: str, fast: bool = False, kernel_spec: dict | None = None
    ) -> str:
        w = cls.workload(fast)
        total_length = w["core_num"] * w["tile_num"] * w["tile_size"]
        gm_inputs, gm_outputs = cls.io_shape(kernel_spec)
        t = cls.dtype(kernel_spec)
        zero = f"({t})0"
        integral = cls.is_integral(t)
        # 没有 kernel_spec 时无独立 golden，只能做 build+launch 冒烟（问题④）：
        # 绝不拿「算子和它自己」比对来制造必然 0 mismatch 的假绿。
        smoke = kernel_spec is None
        input_init = (
            str(kernel_spec.get("input_init")).strip()
            if kernel_spec and kernel_spec.get("input_init")
            else "h_x[i] = static_cast<float>(i); h_y[i] = static_cast<float>(i * 2);"
        )
        golden = (
            str(kernel_spec.get("golden_code")).strip()
            if kernel_spec and kernel_spec.get("golden_code")
            else f"expected = ascend::std::{algo}(x_ref, y_ref);"
        )
        host_vectors = "\n".join(
            [f"    std::vector<{t}> h_in{i}(n);" for i in range(gm_inputs)]
            + [f"    std::vector<{t}> h_out{i}(n);" for i in range(gm_outputs)]
        )
        host_aliases = (
            "    auto& h_x = h_in0;\n"
            + ("    auto& h_y = h_in1;\n" if gm_inputs >= 2 else f"    std::vector<{t}> h_y(n, {zero});\n")
            + "    (void)h_x;\n"
            + "    (void)h_y;\n"
        )
        dev_decls = "\n".join(
            [f"    void* d_in{i} = nullptr;" for i in range(gm_inputs)]
            + [f"    void* d_out{i} = nullptr;" for i in range(gm_outputs)]
        )
        dev_allocs = "\n".join(
            [f"    CHECK_ACL(aclrtMalloc(&d_in{i}, bytes, ACL_MEM_MALLOC_HUGE_FIRST));" for i in range(gm_inputs)]
            + [f"    CHECK_ACL(aclrtMalloc(&d_out{i}, bytes, ACL_MEM_MALLOC_HUGE_FIRST));" for i in range(gm_outputs)]
        )
        input_copies = "\n".join(
            [
                f"    CHECK_ACL(aclrtMemcpy(d_in{i}, bytes, h_in{i}.data(), bytes, ACL_MEMCPY_HOST_TO_DEVICE));"
                for i in range(gm_inputs)
            ]
        )
        launch_args = ", ".join(
            [f"static_cast<uint8_t*>(d_in{i})" for i in range(gm_inputs)]
            + [f"static_cast<uint8_t*>(d_out{i})" for i in range(gm_outputs)]
        )
        output_copies = "\n".join(
            [
                f"    CHECK_ACL(aclrtMemcpy(h_out{i}.data(), bytes, d_out{i}, bytes, ACL_MEMCPY_DEVICE_TO_HOST));"
                for i in range(gm_outputs)
            ]
        )
        final_frees = "\n".join(
            [f"    aclrtFree(d_in{i});" for i in range(gm_inputs)]
            + [f"    aclrtFree(d_out{i});" for i in range(gm_outputs)]
        )

        # ---- 校验/冒烟段 ---- #
        if smoke:
            verify_section = (
                f'    std::cout << "[kernel][{algo}][{KERNEL_SMOKE_MARKER}] no kernel_spec provided: "\n'
                '              << "build + launch + copy-back smoke only; "\n'
                '              << "semantic golden check skipped." << std::endl;\n'
                f'    std::cout << "[kernel][{algo}] ran " << n << " elements (smoke, no golden check)."\n'
                "              << std::endl;\n\n"
            )
            success_line = f"[kernel][{algo}] smoke run finished (unverified; provide a kernel_spec for golden check)."
        else:
            refs = "\n".join(
                [f"        {t} in{i}_ref = h_in{i}[i];" for i in range(gm_inputs)]
                + [
                    "        " + t + " x_ref = in0_ref;",
                    "        " + t + " y_ref = " + ("in1_ref;" if gm_inputs >= 2 else f"{zero};"),
                    "        (void)x_ref;",
                    "        (void)y_ref;",
                ]
                + [f"        (void)in{i}_ref;" for i in range(gm_inputs)]
            )
            expected_vars = "\n".join(
                [f"        {t} expected{i} = {zero};" for i in range(gm_outputs)]
                + [f"        {t}& expected = expected0;", "        (void)expected;"]
                + [f"        (void)expected{i};" for i in range(gm_outputs)]
            )
            output_checks = "\n".join(
                [
                    cls.output_check_block(
                        algo,
                        output_index=i,
                        gm_inputs=gm_inputs,
                        single_output=(gm_outputs == 1),
                        dtype=t,
                    )
                    for i in range(gm_outputs)
                ]
            )
            frees = "\n".join(
                [f"        aclrtFree(d_in{i});" for i in range(gm_inputs)]
                + [f"        aclrtFree(d_out{i});" for i in range(gm_outputs)]
            )
            eps_line = "" if integral else f"    constexpr {t} eps = ({t})1e-5;\n"
            verify_section = (
                f"{eps_line}"
                "    long print_samples = 8;\n"
                '    if (const char* __ps = std::getenv("KERNEL_PRINT_SAMPLES")) {\n'
                "        if (*__ps) print_samples = std::atol(__ps);\n"
                "    }\n"
                "    size_t mismatches = 0;\n"
                "    for (size_t i = 0; i < n; ++i) {\n"
                f"{refs}\n"
                f"{expected_vars}\n"
                f"        {{ {golden} }}\n"
                f"{output_checks}"
                "    }\n"
                f'    std::cout << "[kernel][{algo}] checked " << n << " elements, mismatches "\n'
                "              << mismatches << std::endl;\n"
                "    if (mismatches != 0) {\n"
                f"{frees}\n"
                "        aclrtDestroyStream(stream);\n"
                "        aclrtResetDevice(0);\n"
                "        aclFinalize();\n"
                "        return 2;\n"
                "    }\n\n"
            )
            success_line = KERNEL_VERIFY_MARKER

        return (
            f"// auto-workload={w['tag']} (n={total_length}, cores={w['core_num']}, "
            f"inputs={gm_inputs}, outputs={gm_outputs}, dtype={t})\n"
            '#include "acl/acl.h"\n'
            '#include "host.h"\n'
            f'#include "{include_path}"\n'
            "#include <cmath>\n"
            "#include <cstdlib>\n"
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
            f"    const size_t bytes = n * sizeof({t});\n\n"
            "    CHECK_ACL(aclInit(nullptr));\n"
            "    CHECK_ACL(aclrtSetDevice(0));\n\n"
            "    void* stream = nullptr;\n"
            "    CHECK_ACL(aclrtCreateStream(&stream));\n\n"
            f"{host_vectors}\n"
            f"{host_aliases}"
            "    for (size_t i = 0; i < n; ++i) {\n"
            f"        {{ {input_init} }}\n"
            "    }\n\n"
            f"{dev_decls}\n"
            f"{dev_allocs}\n\n"
            f"{input_copies}\n\n"
            f"    ascend_std_{algo}_do({w['core_num']}, stream, {launch_args});\n"
            "    CHECK_ACL(aclrtSynchronizeStream(stream));\n"
            f"{output_copies}\n\n"
            f"{verify_section}"
            f"{final_frees}\n"
            "    aclrtDestroyStream(stream);\n"
            "    aclrtResetDevice(0);\n"
            "    aclFinalize();\n\n"
            f'    std::cout << "{success_line}" << std::endl;\n'
            "    return 0;\n"
            "}\n"
        )

    @staticmethod
    def output_check_block(
        algo: str,
        *,
        output_index: int,
        gm_inputs: int,
        single_output: bool,
        dtype: str = "float",
    ) -> str:
        got = f"got{output_index}"
        expected = f"expected{output_index}"
        label = "" if single_output else f"[out{output_index}]"
        input_stream = "".join([f' << " in{i}=" << in{i}_ref' for i in range(gm_inputs)])
        # 整型用精确相等；浮点用 eps 容差（main.cpp 里已声明 eps）。
        if KernelScaffoldBuilder.is_integral(dtype):
            mismatch_cond = f"{got} != {expected}"
        else:
            mismatch_cond = f"std::abs({got} - {expected}) > eps"
        return (
            f"        {dtype} {got} = h_out{output_index}[i];\n"
            "        if (print_samples < 0 || static_cast<long>(i) < print_samples) {\n"
            f'            std::cout << "[kernel][{algo}][" << i << "]{label}"{input_stream}\n'
            f'                      << " got=" << {got} << " expected=" << {expected} << std::endl;\n'
            "        }\n"
            f"        if ({mismatch_cond}) {{\n"
            "            ++mismatches;\n"
            "            if (mismatches <= 8) {\n"
            f'                std::cerr << "Mismatch at i=" << i << ", out{output_index}, got=" << {got}\n'
            f'                          << ", expected=" << {expected} << std::endl;\n'
            "            }\n"
            "        }\n"
        )

    @classmethod
    def cmakelists(cls, soc_version: str = KERNEL_SOC_VERSION) -> str:
        return (
            "cmake_minimum_required(VERSION 3.16)\n"
            "project(Ascend_c)\n\n"
            f'set(SOC_VERSION "{soc_version}" CACHE STRING "system on chip type")\n'
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
            "target_link_options(ascendc_kernels_bbit PRIVATE\n"
            "    -Wl,--allow-shlib-undefined\n"
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

    @staticmethod
    def npu_lib_cmake() -> str:
        """`cmake/npu_lib.cmake`：定位 CANN 的 ascendc_kernel_cmake 并声明 kernel 库。

        历史上这份文件以「目标仓 max_example/cmake 拷贝到其它算子」的方式复用——等于把
        目标仓（输出）当成模板输入，违反「输入只在源仓/examples、输出只在目标仓/outputs」。
        现与其它脚手架一致由代码生成（单一事实源），目标仓里的 cmake/ 纯属输出。
        """
        return (
            "# *****************************************************************************\n"
            "# Copyright (c) 2026 Xiong Shengwu Group at Wuhan University of Technology. All Rights Reserved.\n"
            "# Author: Lu Xiongbo <luxiongbo@whut.edu.cn>\n"
            "# Create: 2026-01-19\n"
            "#\n"
            '# Licensed under the Apache License, Version 2.0 (the "License");\n'
            "# you may not use this file except in compliance with the License.\n"
            "# You may obtain a copy of the License at\n"
            "#\n"
            "# http://www.apache.org/licenses/LICENSE-2.0\n"
            "#\n"
            "# Unless required by applicable law or agreed to in writing, software\n"
            '# distributed under the License is distributed on an "AS IS" BASIS,\n'
            "# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.\n"
            "# See the License for the specific language governing permissions and\n"
            "# limitations under the License.\n"
            "# *****************************************************************************\n"
            "\n"
            "if(EXISTS ${ASCEND_CANN_PACKAGE_PATH}/compiler/tikcpp/ascendc_kernel_cmake)\n"
            "    set(ASCENDC_CMAKE_DIR ${ASCEND_CANN_PACKAGE_PATH}/compiler/tikcpp/ascendc_kernel_cmake)\n"
            "elseif(EXISTS ${ASCEND_CANN_PACKAGE_PATH}/tools/tikcpp/ascendc_kernel_cmake)\n"
            "    set(ASCENDC_CMAKE_DIR ${ASCEND_CANN_PACKAGE_PATH}/tools/tikcpp/ascendc_kernel_cmake)\n"
            "else()\n"
            '    message(FATAL_ERROR "ascendc_kernel_cmake does not exist ,please check whether the cann package is installed")\n'
            "endif()\n"
            "include(${ASCENDC_CMAKE_DIR}/ascendc.cmake)\n"
            "ascendc_library(ascendc_kernels_${RUN_MODE} SHARED ${KERNEL_FILES})\n"
        )

    # shell 脚本生成已拆分到 core/scaffold_scripts.py（run_test_sh / host_run_test_sh /
    # full_project_run_sh），本类专注 AscendC/ACL 的 C++ 源与 CMake 生成。
