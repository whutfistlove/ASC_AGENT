"""模型客户端。

改进：
1. 抽象出统一接口 BaseModelClient，真实实现 ZhipuModelClient 与
   测试/演示用 MockModelClient 都遵循同一接口，pipeline 通过依赖注入使用，
   因此可以在没有 API Key、不联网的情况下完整跑通整条流程并写测试。
2. normalize 由配置开关控制；预处理指令空格的正则从 v2 的 3 条推广为一条，
   覆盖 define/else/endif/if/ifdef/ifndef/elif/include/pragma/undef。
"""

from __future__ import annotations

import json
import os
import re
from typing import Callable, Optional, Protocol, runtime_checkable


# --------------------------------------------------------------------------- #
# 接口
# --------------------------------------------------------------------------- #
@runtime_checkable
class BaseModelClient(Protocol):
    def generate(
        self,
        *,
        system_prompt: str,
        user_content: str,
        on_delta: Optional[Callable[[str], None]] = None,
    ) -> str:
        ...


def _parse_tool_args(raw) -> dict:
    """tool_call.arguments 可能是 JSON 字符串或 dict，统一成 dict。"""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            obj = json.loads(raw)
            return obj if isinstance(obj, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


# --------------------------------------------------------------------------- #
# 真实实现：智谱（OpenAI 兼容 REST 接口）
# --------------------------------------------------------------------------- #
class ZhipuModelClient:
    """直接对接智谱开放平台的 OpenAI 兼容接口。

    官方接入方式（与本实现一致）：

        POST https://open.bigmodel.cn/api/paas/v4/chat/completions
        Authorization: Bearer <api-key>
        Content-Type: application/json
        {
          "model": "glm-5",
          "messages": [{"role": "user", "content": "..."}],
          "thinking": {"type": "enabled"},
          "stream": false,
          "max_tokens": 65536,
          "temperature": 1.0
        }

    之前的实现依赖第三方 `zai` SDK 的 `ZhipuAiClient`，与官方文档的
    Bearer + REST 调用方式不一致；这里改为标准 HTTP 调用，便于排错与对照文档。
    """

    DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    def __init__(
        self,
        model_name: str,
        api_key_env: str = "ZHIPU_API_KEY",
        base_url: str = "",
        temperature: float = 0.6,
        max_tokens: int = 65536,
        thinking: bool = False,
        response_format_json: bool = True,
        stream: bool = True,
        timeout: int = 600,
    ):
        self.model_name = model_name
        self.api_key_env = api_key_env
        self.base_url = base_url or self.DEFAULT_BASE_URL
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.thinking = thinking
        self.response_format_json = response_format_json
        self.stream = stream
        self.timeout = timeout

    def _api_key(self) -> str:
        try:
            from dotenv import load_dotenv

            load_dotenv()
        except Exception:
            pass  # dotenv 可选，缺失时退回手动解析 .env / 进程环境变量
        api_key = os.getenv(self.api_key_env) or self._read_key_from_dotenv()
        if not api_key:
            raise ValueError(f"未读取到 {self.api_key_env}，请检查 .env 文件或环境变量")
        return api_key

    def _read_key_from_dotenv(self) -> str:
        """python-dotenv 未安装时的兜底：手动从就近的 .env 读取 key=value。"""
        here = os.path.abspath(os.getcwd())
        for base in (here, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))):
            env_path = os.path.join(base, ".env")
            if not os.path.exists(env_path):
                continue
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        name, _, value = line.partition("=")
                        if name.strip() == self.api_key_env:
                            return value.strip().strip('"').strip("'")
            except OSError:
                continue
        return ""

    def _build_payload(self, system_prompt: str, user_content: str) -> dict:
        payload: dict = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "stream": self.stream,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if self.thinking:
            payload["thinking"] = {"type": "enabled"}
        if self.response_format_json:
            # 让模型直接吐合法 JSON 对象，配合 extract_json_object 更稳
            payload["response_format"] = {"type": "json_object"}
        return payload

    def generate(
        self,
        *,
        system_prompt: str,
        user_content: str,
        on_delta: Optional[Callable[[str], None]] = None,
    ) -> str:
        import requests  # 延迟导入，避免 mock/离线路径强依赖

        headers = {
            "Authorization": f"Bearer {self._api_key()}",
            "Content-Type": "application/json",
        }
        payload = self._build_payload(system_prompt, user_content)
        if self.stream:
            return self._generate_stream(requests, headers, payload, on_delta)
        return self._generate_once(requests, headers, payload)

    def generate_with_tools(
        self,
        *,
        system_prompt: str,
        user_content: str,
        tool_schemas: list,
        dispatch,
        max_tool_rounds: int = 4,
        on_delta: Optional[Callable[[str], None]] = None,
    ) -> str:
        """带工具调用的多轮对话（OpenAI 兼容 tools）。

        模型可多轮调用 read_repo_file / grep_repo / host_syntax_check / extract_error_lines
        取证与自检；无更多 tool_calls 时返回其最终 content（应为 JSON）。dispatch(name, args)
        由调用方提供（通常是 AgentToolbox.dispatch），返回工具结果字符串。
        """
        import requests  # 延迟导入

        headers = {
            "Authorization": f"Bearer {self._api_key()}",
            "Content-Type": "application/json",
        }
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
        for _ in range(max_tool_rounds):
            payload = {
                "model": self.model_name,
                "messages": messages,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
                "stream": False,
                "tools": tool_schemas,
            }
            msg = self._post_chat(requests, headers, payload)
            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                content = msg.get("content") or ""
                if on_delta and content:
                    on_delta(content)
                return content
            messages.append(
                {"role": "assistant", "content": msg.get("content") or "", "tool_calls": tool_calls}
            )
            for tc in tool_calls:
                fn = tc.get("function", {}) or {}
                args = _parse_tool_args(fn.get("arguments"))
                result = dispatch(fn.get("name", ""), args)
                if on_delta:
                    on_delta(f"\n[tool:{fn.get('name','')}] -> {str(result)[:200]}\n")
                messages.append(
                    {"role": "tool", "tool_call_id": tc.get("id", ""), "content": str(result)}
                )
        # 超过最大工具轮数：再要一次「不带工具」的最终回答（强制 JSON）。
        final_payload = {
            "model": self.model_name,
            "messages": messages
            + [{"role": "user", "content": "请基于以上调查结果，现在只输出最终 JSON 对象。"}],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False,
        }
        if self.response_format_json:
            final_payload["response_format"] = {"type": "json_object"}
        msg = self._post_chat(requests, headers, final_payload)
        content = msg.get("content") or ""
        if on_delta and content:
            on_delta(content)
        return content

    def _post_chat(self, requests, headers: dict, payload: dict) -> dict:
        """非流式 POST，返回 choices[0].message（含可能的 tool_calls）。"""
        resp = requests.post(self.base_url, headers=headers, json=payload, timeout=self.timeout)
        if resp.status_code != 200:
            raise RuntimeError(f"智谱接口返回 {resp.status_code}: {resp.text[:500]}")
        data = resp.json()
        try:
            return data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"无法从智谱响应中解析 message: {data}") from exc

    def _generate_once(self, requests, headers: dict, payload: dict) -> str:
        resp = requests.post(self.base_url, headers=headers, json=payload, timeout=self.timeout)
        if resp.status_code != 200:
            raise RuntimeError(f"智谱接口返回 {resp.status_code}: {resp.text[:500]}")
        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"无法从智谱响应中解析 content: {data}") from exc

    def _generate_stream(self, requests, headers: dict, payload: dict,
                         on_delta: Optional[Callable[[str], None]]) -> str:
        """SSE 流式：逐块累积 content 并返回完整文本；有 on_delta 时实时回调增量。

        thinking 开启时，reasoning_content 也会通过 on_delta 实时回显，
        但只把正式 content 累积进返回值（保证返回的是干净的 JSON 文本）。
        """
        parts: list[str] = []
        with requests.post(
            self.base_url, headers=headers, json=payload, timeout=self.timeout, stream=True
        ) as resp:
            if resp.status_code != 200:
                raise RuntimeError(f"智谱接口返回 {resp.status_code}: {resp.text[:500]}")
            for raw_line in resp.iter_lines(decode_unicode=True):
                if not raw_line:
                    continue
                line = raw_line.strip()
                if line.startswith("data:"):
                    line = line[len("data:"):].strip()
                if not line:
                    continue
                if line == "[DONE]":
                    break
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                reasoning = delta.get("reasoning_content")
                if reasoning and on_delta:
                    on_delta(reasoning)
                piece = delta.get("content")
                if piece:
                    parts.append(piece)
                    if on_delta:
                        on_delta(piece)
        if not parts:
            raise RuntimeError("智谱流式响应未返回任何 content（请检查 model/参数或改用非流式）")
        return "".join(parts)


# --------------------------------------------------------------------------- #
# 测试 / 演示实现：Mock
# --------------------------------------------------------------------------- #
class MockModelClient:
    """可脚本化的假客户端。

    - 传入 responses 列表：按顺序返回（适合单测里精确控制初稿 + 各轮修复）。
    - 不传：根据请求里的 expected_header_guard 现编一个合理的 ACCL 头文件，
      用于无网络的端到端演示，顺带验证 guard 的端到端串联。
    """

    def __init__(self, responses: Optional[list[str]] = None, tool_script: Optional[list[dict]] = None):
        self._responses = list(responses) if responses else None
        # tool_script：[{"name": "read_repo_file", "arguments": {...}}, ...]，
        # generate_with_tools 会先逐个 dispatch（模拟模型取证），再返回最终 JSON。
        self._tool_script = list(tool_script) if tool_script else None
        self.calls: list[dict] = []

    def generate(
        self,
        *,
        system_prompt: str,
        user_content: str,
        on_delta: Optional[Callable[[str], None]] = None,
    ) -> str:
        self.calls.append({"system_prompt": system_prompt, "user_content": user_content})
        if self._responses is not None:
            if not self._responses:
                raise AssertionError("MockModelClient 预设响应已耗尽")
            return self._responses.pop(0)
        return self._auto_response(user_content)

    def generate_with_tools(
        self,
        *,
        system_prompt: str,
        user_content: str,
        tool_schemas: list,
        dispatch,
        max_tool_rounds: int = 4,
        on_delta: Optional[Callable[[str], None]] = None,
    ) -> str:
        """离线模拟带工具的对话：先按 tool_script 调用工具，再返回最终响应。"""
        self.calls.append({"system_prompt": system_prompt, "user_content": user_content, "tools": True})
        for call in (self._tool_script or [])[:max_tool_rounds]:
            dispatch(call.get("name", ""), call.get("arguments", {}))
        return self.generate(system_prompt=system_prompt, user_content=user_content, on_delta=on_delta)

    @staticmethod
    def _extract_field(text: str, label: str) -> str:
        # 解析形如「【label】\n值」的块
        m = re.search(rf"【{re.escape(label)}】\s*\n([^\n【]+)", text)
        return m.group(1).strip() if m else ""

    def _auto_response(self, user_content: str) -> str:
        guard = self._extract_field(user_content, "expected_header_guard") or "ACCL_GENERATED_H_"
        is_fix = "post-hook 基线" in user_content

        if is_fix:
            # 修复阶段：原样返回基线（pipeline 会识别“无变化”并继续轮转）
            m = re.search(r"【当前 post-hook 基线文件内容】\s*\n(.*?)\n【", user_content, re.S)
            baseline = m.group(1) if m else ""
            payload = {
                "rewritten_code": baseline,
                "notes": "mock：本轮未做实质改动（演示用）。",
            }
            return json.dumps(payload, ensure_ascii=False)

        code = (
            f"#ifndef {guard}\n"
            f"#define {guard}\n\n"
            f"// mock-generated ACCL draft (no copyright header on purpose)\n"
            f"#define _ACCL_OS(...) _ACCL_OS_##__VA_ARGS__##_()\n\n"
            f"#endif  // {guard}\n"
        )
        payload = {
            "file_type": "mock_header",
            "rewritten_code": code,
            "notes": "mock：演示用初稿，由 expected_header_guard 现场生成。",
        }
        return json.dumps(payload, ensure_ascii=False)


# --------------------------------------------------------------------------- #
# 工厂
# --------------------------------------------------------------------------- #
def build_model_client(config) -> BaseModelClient:
    provider = config.model_provider
    if provider == "mock":
        return MockModelClient()
    if provider == "zhipu":
        return ZhipuModelClient(
            model_name=config.model_name,
            api_key_env=config.api_key_env,
            base_url=config.model_base_url,
            temperature=config.model_temperature,
            max_tokens=config.model_max_tokens,
            thinking=config.model_thinking,
            response_format_json=config.model_response_format_json,
            stream=config.model_stream,
        )
    raise ValueError(f"未知的 model.provider: {provider}")


# --------------------------------------------------------------------------- #
# 解析与归一化
# --------------------------------------------------------------------------- #
def extract_json_object(text: str, *, strict: bool = False) -> dict:
    """从模型输出中提取 JSON 对象。

    默认保持历史兼容：允许模型在 JSON 前后夹带少量解释。strict=True 用于
    已明确要求“只输出 JSON”的链路，任何 Markdown/额外说明都会被拒绝。
    """
    cleaned = text.strip()
    if strict:
        try:
            obj = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise ValueError("模型输出必须是单个 JSON 对象，不能包含 Markdown 或额外解释") from exc
        if not isinstance(obj, dict):
            raise ValueError(f"模型输出 JSON 必须是对象，实际为: {type(obj).__name__}")
        return obj

    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("模型输出中未找到合法 JSON 对象")
    obj = json.loads(cleaned[start : end + 1])
    if not isinstance(obj, dict):
        raise ValueError(f"模型输出 JSON 必须是对象，实际为: {type(obj).__name__}")
    return obj


_DIRECTIVE_RE = re.compile(
    r"^#[ \t]+(define|else|endif|if|ifdef|ifndef|elif|include|pragma|undef)\b",
    flags=re.MULTILINE,
)


def normalize_generated_text(text: str, options: Optional[dict] = None) -> str:
    """轻量归一化，去掉明显格式噪音。具体行为由 options 开关控制。"""
    options = options or {}
    text = text.lstrip()
    if options.get("fix_directive_spacing", True):
        text = _DIRECTIVE_RE.sub(lambda m: "#" + m.group(1), text)
    if options.get("ensure_trailing_newline", True):
        text = text.rstrip() + "\n"
    return text
