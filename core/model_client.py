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

    def __init__(self, responses: Optional[list[str]] = None):
        self._responses = list(responses) if responses else None
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
def extract_json_object(text: str) -> dict:
    """稳健地从模型输出中提取 JSON 对象。"""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("模型输出中未找到合法 JSON 对象")
    return json.loads(cleaned[start : end + 1])


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
