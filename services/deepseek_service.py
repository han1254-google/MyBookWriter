"""
DeepSeek API 服务（Anthropic Messages 兼容端点）
"""
import json
import urllib.request
import urllib.error
from app_config import DEEPSEEK_BASE_URL, DEEPSEEK_API_KEY, DEEPSEEK_MODEL, DEEPSEEK_FLASH_MODEL


class DeepSeekService:
    """DeepSeek API 客户端（Anthropic 兼容接口）"""

    def __init__(self, model=None):
        self.base_url = DEEPSEEK_BASE_URL.rstrip("/")
        self.api_key = DEEPSEEK_API_KEY
        self.model = model or DEEPSEEK_MODEL

    def _make_request(self, messages, system_prompt="", max_tokens=4096, stream=False):
        """发送请求到 DeepSeek Anthropic 兼容端点"""
        url = f"{self.base_url}/v1/messages"
        body = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
            "stream": stream,
        }
        if system_prompt:
            body["system"] = system_prompt

        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("x-api-key", self.api_key)
        req.add_header("anthropic-version", "2023-06-01")
        req.add_header("Content-Type", "application/json")

        return urllib.request.urlopen(req, timeout=300)

    def chat(self, user_message, system_prompt="", history=None, max_tokens=4096):
        """
        同步聊天，返回完整文本。
        history: [{"role": "user"|"assistant", "content": "..."}]
        """
        messages = []
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        try:
            resp = self._make_request(messages, system_prompt, max_tokens, stream=False)
            body = json.loads(resp.read().decode("utf-8"))
            # Anthropic 格式: content[0].text
            if "content" in body and isinstance(body["content"], list):
                return "".join(block.get("text", "") for block in body["content"])
            return ""
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"DeepSeek API 错误 (HTTP {e.code}): {error_body}")
        except Exception as e:
            raise RuntimeError(f"DeepSeek API 请求失败: {e}")

    def chat_stream(self, user_message, system_prompt="", history=None, max_tokens=4096):
        """
        流式聊天，逐块 yield 文本。
        """
        messages = []
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        try:
            resp = self._make_request(messages, system_prompt, max_tokens, stream=True)

            # 逐行读取 SSE 流
            buffer = b""
            while True:
                chunk = resp.read(1024)
                if not chunk:
                    break
                buffer += chunk

                # 按行分割
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    line = line.strip()
                    if not line:
                        continue

                    # Anthropic SSE 格式: "data: {...}" 或 "event: ..."
                    if line.startswith(b"data: "):
                        json_str = line[6:]
                        try:
                            event = json.loads(json_str)
                            # 提取 delta text
                            if event.get("type") == "content_block_delta":
                                delta = event.get("delta", {})
                                text = delta.get("text", "")
                                if text:
                                    yield text
                            elif event.get("type") == "message_stop":
                                return
                        except json.JSONDecodeError:
                            continue
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            yield f"\n\n[错误 HTTP {e.code}: {error_body}]"
        except Exception as e:
            yield f"\n\n[错误: {e}]"


# 全局实例
deepseek = DeepSeekService()
deepseek_flash = DeepSeekService(model=DEEPSEEK_FLASH_MODEL)
