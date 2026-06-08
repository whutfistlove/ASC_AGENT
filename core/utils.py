from __future__ import annotations

import sys
from pathlib import Path


def save_text(path: Path, content: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # 显式 newline="\n"：禁止 Python 在任何平台把 "\n" 翻译成 "\r\n"。
    # 生成的 .sh 一旦带 CRLF，bash 下 `set -e` 会失效并产生假阳性。
    path.write_text(content, encoding="utf-8", newline="\n")


def read_text_file(path_str: str) -> str:
    path = Path(path_str).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {path}")
    return path.read_text(encoding="utf-8")


def call_model_with_io(model, *, stage: str, system_prompt: str, user_content: str,
                       show_io: bool) -> str:
    """调用模型并返回完整响应文本。

    - show_io=False：直接调用并返回（流式仍在底层进行，只是不回显）。
    - show_io=True：打印 system 提示词 + 完整请求，并通过 on_delta 把响应**实时逐字**
      打印出来（流式）；若客户端非流式 / mock 未触发增量，则在结束后一次性打印完整响应。
    """
    if not show_io:
        return model.generate(system_prompt=system_prompt, user_content=user_content)

    sep = "=" * 72
    print(f"\n{sep}")
    print(f"[模型交互] {stage} —— system_prompt（提示词）")
    print(sep)
    print(system_prompt)
    print(f"\n{sep}")
    print(f"[模型交互] {stage} —— user_content（发给模型的完整请求）")
    print(sep)
    print(user_content)
    print(f"\n{sep}")
    print(f"[模型交互] {stage} —— 模型响应（流式逐字）")
    print(sep)

    streamed = {"any": False}

    def on_delta(text: str) -> None:
        streamed["any"] = True
        sys.stdout.write(text)
        sys.stdout.flush()

    raw = model.generate(system_prompt=system_prompt, user_content=user_content, on_delta=on_delta)
    if streamed["any"]:
        print()  # 流式结束后补一个换行
    else:
        print(raw)  # 非流式 / mock：一次性打印
    print(f"{sep}\n")
    return raw


def call_model_maybe_tools(model, *, stage: str, system_prompt: str, user_content: str,
                           show_io: bool, toolbox=None, max_tool_rounds: int = 4,
                           tool_log_tag: str = "") -> str:
    """有 toolbox 且客户端支持时走「带工具」对话，否则回退到单轮 generate。

    toolbox 提供 schemas() 与 dispatch(name, args)；这样客户端与具体工具实现解耦，
    便于离线 mock 测试整条带工具的修复链路。tool_log_tag 给出时把本阶段的工具调用
    审计落盘到 outputs/tool_calls_<tag>.json，并打印一行摘要（模型有没有调用工具一目了然）。
    """
    if toolbox is None or not hasattr(model, "generate_with_tools"):
        return call_model_with_io(
            model, stage=stage, system_prompt=system_prompt, user_content=user_content, show_io=show_io
        )

    on_delta = None
    if show_io:
        sep = "=" * 72
        print(f"\n{sep}\n[模型交互·带工具] {stage} —— system\n{sep}\n{system_prompt}")
        print(f"\n{sep}\n[模型交互·带工具] {stage} —— user\n{sep}\n{user_content}")
        print(f"\n{sep}\n[模型交互·带工具] {stage} —— 调查/响应\n{sep}")

        def on_delta(text: str) -> None:  # noqa: E306
            sys.stdout.write(text)
            sys.stdout.flush()

    before = len(getattr(toolbox, "call_log", []) or [])
    raw = model.generate_with_tools(
        system_prompt=system_prompt,
        user_content=user_content,
        tool_schemas=toolbox.schemas(),
        dispatch=toolbox.dispatch,
        max_tool_rounds=max_tool_rounds,
        on_delta=on_delta,
    )
    if show_io:
        print(f"\n{'=' * 72}\n")

    # 工具调用审计：落盘 + 一行摘要，把「模型有没有调用辅助工具」变成可见、可查的硬证据。
    # 这里统计的是模型会话内部的 repo 读取/grep/语法检查等辅助工具，不是主模型请求次数。
    calls = list(getattr(toolbox, "call_log", []) or [])
    this_stage = calls[before:]
    names = ", ".join(c.get("name", "?") for c in this_stage) or "无"
    print(f"[tools] {stage}：本阶段 AI 辅助工具调用 {len(this_stage)} 次（{names}）")
    if tool_log_tag and hasattr(toolbox, "dump_call_log") and getattr(toolbox, "output_dir", None):
        try:
            toolbox.dump_call_log(Path(toolbox.output_dir) / f"tool_calls_{tool_log_tag}.json")
        except Exception:
            pass
    return raw
