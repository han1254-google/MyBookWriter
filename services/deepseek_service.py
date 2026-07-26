"""
DeepSeek API 服务（Anthropic Messages 兼容端点）
"""
import json
import time
import urllib.request
import urllib.error
from app_config import DEEPSEEK_BASE_URL, DEEPSEEK_API_KEY, DEEPSEEK_MODEL, DEEPSEEK_FLASH_MODEL
from logger import get_logger

log = get_logger("service.deepseek")


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

        last_msg = messages[-1]["content"][:60] if messages else ""
        log.debug(f"API请求: model={self.model}, max_tokens={max_tokens}, stream={stream}, prompt={last_msg}...")
        t0 = time.time()

        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("x-api-key", self.api_key)
        req.add_header("anthropic-version", "2023-06-01")
        req.add_header("Content-Type", "application/json")

        try:
            resp = urllib.request.urlopen(req, timeout=300)
            elapsed = (time.time() - t0) * 1000
            log.debug(f"API响应: model={self.model}, status={resp.status}, {elapsed:.0f}ms")
            return resp
        except urllib.error.HTTPError as e:
            elapsed = (time.time() - t0) * 1000
            error_body = e.read().decode("utf-8", errors="replace")
            log.error(f"API HTTP错误: model={self.model}, code={e.code}, {elapsed:.0f}ms, body={error_body[:300]}")
            raise

    def chat(self, user_message, system_prompt="", history=None, max_tokens=4096):
        """
        同步聊天，返回完整文本。
        history: [{"role": "user"|"assistant", "content": "..."}]
        """
        messages = []
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        t0 = time.time()
        try:
            resp = self._make_request(messages, system_prompt, max_tokens, stream=False)
            body = json.loads(resp.read().decode("utf-8"))
            if "content" in body and isinstance(body["content"], list):
                text = "".join(block.get("text", "") for block in body["content"])
                elapsed = (time.time() - t0) * 1000
                log.info(f"chat完成: model={self.model}, {len(text)} 字符, {elapsed:.0f}ms")
                return text
            return ""
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            log.error(f"chat HTTP错误: model={self.model}, code={e.code}, body={error_body[:200]}")
            raise RuntimeError(f"DeepSeek API 错误 (HTTP {e.code}): {error_body}")
        except Exception as e:
            log.error(f"chat失败: model={self.model}, {type(e).__name__}: {e}", exc_info=True)
            raise RuntimeError(f"DeepSeek API 请求失败: {e}")

    def chat_stream(self, user_message, system_prompt="", history=None, max_tokens=4096):
        """
        流式聊天，逐块 yield 文本。
        """
        messages = []
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        chunk_count = 0
        total_chars = 0
        t0 = time.time()
        try:
            resp = self._make_request(messages, system_prompt, max_tokens, stream=True)

            buffer = b""
            while True:
                chunk = resp.read(1024)
                if not chunk:
                    break
                buffer += chunk

                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    line = line.strip()
                    if not line:
                        continue

                    if line.startswith(b"data: "):
                        json_str = line[6:]
                        try:
                            event = json.loads(json_str)
                            if event.get("type") == "content_block_delta":
                                text = event.get("delta", {}).get("text", "")
                                if text:
                                    chunk_count += 1
                                    total_chars += len(text)
                                    yield text
                            elif event.get("type") == "message_stop":
                                elapsed = (time.time() - t0) * 1000
                                log.info(f"chat_stream完成: model={self.model}, {total_chars}字符/{chunk_count}块, {elapsed:.0f}ms")
                                return
                        except json.JSONDecodeError:
                            continue
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            log.error(f"chat_stream HTTP错误: model={self.model}, code={e.code}")
            yield f"\n\n[错误 HTTP {e.code}: {error_body}]"
        except Exception as e:
            log.error(f"chat_stream失败: model={self.model}, {type(e).__name__}: {e}", exc_info=True)
            yield f"\n\n[错误: {e}]"


# 全局实例
deepseek = DeepSeekService()
deepseek_flash = DeepSeekService(model=DEEPSEEK_FLASH_MODEL)
