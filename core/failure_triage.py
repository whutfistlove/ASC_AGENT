"""把 host/kernel 测试失败分类为「环境问题」还是「代码问题」。

动机（见 outputs/fix_notes_test_round1..3.md）：sort3 的三轮修复全部白烧，因为真正的
失败是环境问题（旧 CMakeCache、缺 llvm-objdump、缺驱动库），改代码无济于事，模型每轮都
正确地说"这是环境问题"，但循环没有这层判定，于是反复调用模型、甚至无谓改写正确代码。

约定：
    * ``env``     —— 构建/工具链/驱动/模拟器配置问题。改代码无用，不应进模型修复循环。
    * ``code``    —— 编译错误、数值 Mismatch、被测符号缺失等。模型修复有意义。
    * ``unknown`` —— 无法判定（信息不足）。调用方按需决定是否仍尝试一次模型修复。
"""

from __future__ import annotations

from dataclasses import dataclass

ENV = "env"
CODE = "code"
UNKNOWN = "unknown"

# 代码类特征：命中即判 code（这些是模型能改的东西）。优先于 env，因为真正的编译/数值错
# 总是值得回传模型；纯环境失败通常不含这些行（工具链/驱动错发生在编译成功之后）。
_CODE_SIGNATURES = (
    "error: no matching function",
    "error: no member named",
    "error: use of undeclared identifier",
    "error: expected ",
    "error: cannot convert",
    "error: too few arguments",
    "error: too many arguments",
    "error: redefinition",
    "incompatible type",
    "candidate function template not viable",
    "static_assert",
    "Mismatch at",  # kernel 数值校验失败：算子/golden 写错
)

# 环境类特征：命中即判 env（改代码无用，应修环境或跳过）。
_ENV_SIGNATURES = (
    "is different than the directory",  # 过期 CMakeCache（项目改名/移动）
    "does not match the source",  # 同上
    "llvm-objdump",  # CANN 工具链缺失
    "cannsim command not found",  # 模拟器未安装/未启用
    "cannsim: command not found",
    "No such file or directory: 'llvm-objdump'",
    "undefined reference to `drv",  # 驱动/HAL 链接：模拟器驱动库未配
    "undefined reference to `hal",
    "undefined reference to `ge::",  # CANN GE/register 间接依赖/链接策略问题
    "undefined reference to `gert::",
    "undefined reference to `optiling::",
    "libascend_hal",
    "libregister.so",
    "symbol lookup error",  # CANN runtime picked an incompatible shared library copy
    "undefined symbol: _ZNK2ge12AscendString",
    "undefined symbol: _ZN2ge9GetTypeId",
    "SOC_VERSION",
    "does not support, the support list is",
    "未找到 bash",
    "未找到 Ascend 环境脚本",
    "CMake Error: The current CMakeCache",
)


@dataclass
class FailureTriage:
    kind: str = UNKNOWN  # env | code | unknown
    reason: str = ""  # 命中的特征片段，便于人读

    @property
    def is_env(self) -> bool:
        return self.kind == ENV

    @property
    def is_code(self) -> bool:
        return self.kind == CODE


def classify_failure(log_text: str | None) -> FailureTriage:
    """根据日志文本判定失败类型。代码特征优先于环境特征。"""
    if not log_text:
        return FailureTriage(UNKNOWN, "")
    for sig in _CODE_SIGNATURES:
        if sig in log_text:
            return FailureTriage(CODE, sig)
    for sig in _ENV_SIGNATURES:
        if sig in log_text:
            return FailureTriage(ENV, sig)
    return FailureTriage(UNKNOWN, "")
