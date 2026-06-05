"""best-of-N 生成：一次采样多个候选，用「便宜的校验器」打分，择优落定。

动机：本项目能**廉价地验证**产物——host 测试可 `g++ -fsyntax-only` 自检、头文件可做
结构校验。既然验证比生成便宜，就该一次多采样、挑能过校验的那个，提升一次成功率，而不是
单发一个就硬着头皮往下走。`n=1` 时退化为单发（行为完全不变），>1 才进入择优。

设计：生成/解析/打分都由调用方注入，模块本身不知道在迁头还是迁测试，便于离线单测。
解析失败的候选记为无效；全部无效时**抛出最后一次解析错误**（与单发语义一致，不吞错）。
"""

from __future__ import annotations

from typing import Callable


def best_of_n(
    generate: Callable[[], str],
    parse: Callable[[str], object],
    score: Callable[[object], float],
    *,
    n: int,
) -> tuple[object, str, list[float]]:
    """采样 n 次并择优。

    返回 (best_parsed, best_raw, all_scores)。`all_scores` 与采样顺序对齐，解析失败记
    `-inf`，便于上层日志查看离散度。
    """
    parsed_list: list[tuple[float, str, object]] = []
    last_parse_error: Exception | None = None
    for _ in range(max(1, int(n))):
        raw = generate()
        try:
            parsed = parse(raw)
        except Exception as exc:  # 单个候选解析失败不致命，继续采样
            last_parse_error = exc
            parsed_list.append((float("-inf"), raw, None))
            continue
        parsed_list.append((score(parsed), raw, parsed))

    valid = [(s, raw, p) for (s, raw, p) in parsed_list if p is not None]
    if not valid:
        if last_parse_error is not None:
            raise last_parse_error
        raise ValueError("best_of_n：没有可用候选")
    best = max(valid, key=lambda t: t[0])
    return best[2], best[1], [s for (s, _r, _p) in parsed_list]


# --------------------------------------------------------------------------- #
# 内置打分器（纯函数，便于离线复用与单测）
# --------------------------------------------------------------------------- #
def score_header_code(code: str, guard: str) -> float:
    """头文件候选的结构打分（离线、确定性）：guard 正确 + 预处理指令配平更优。

    不做完整编译（孤立头缺宏定义难以可靠编译）；结构信号已能把「丢了 guard / `#endif`
    不配平 / 空壳」这类明显劣质候选区分开。
    """
    if not isinstance(code, str) or not code.strip():
        return float("-inf")
    s = 0.0
    if guard:
        if f"#ifndef {guard}" in code:
            s += 1.0
        if f"#define {guard}" in code:
            s += 1.0
        if "#endif" in code and guard in code.split("#endif")[-1]:
            s += 0.5  # #endif // GUARD 收尾注释
    opens = sum(code.count(d) for d in ("#ifndef", "#ifdef", "#if "))
    closes = code.count("#endif")
    if opens and opens == closes:
        s += 1.0
    elif opens != closes:
        s -= 1.0  # 预处理指令不配平：几乎必编译失败
    if "ascend::std" in code or "_ASCEND" in code:
        s += 0.5  # 命中目标命名空间/宏，更像真正迁好的产物
    return s


def score_host_test_code(code: str, toolbox=None) -> float:
    """host 测试候选打分：有 toolbox 且有 g++ 时以 `-fsyntax-only` 自检为主信号。

    g++ 缺失（如 CI 无编译器）时降级为结构打分，所有候选趋同→稳定选第一个（不劣化）。
    """
    if not isinstance(code, str) or not code.strip():
        return float("-inf")
    s = 0.0
    if "int main" in code:
        s += 1.0
    if "#include" in code:
        s += 0.5
    if toolbox is not None and hasattr(toolbox, "host_syntax_check"):
        res = toolbox.host_syntax_check(code)
        if isinstance(res, str):
            if res.startswith("OK"):
                s += 100.0          # 真能编译，强烈优先
            elif res.startswith("FAILED"):
                s -= 10.0           # 编译失败，强烈劣后
            # 「未找到编译器」等中性信息：不加不减
    return s
