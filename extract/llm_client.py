"""OpenAI 兼容的 Chat Completions 客户端。

厂商差异只在这一层：换厂商只改 env（base_url / key / model）。
裸 HTTP 实现，仅依赖 requests，可对接任意 OpenAI 兼容端点。
"""
import time
import logging
import random

import requests

logger = logging.getLogger(__name__)


class LLMError(Exception):
    pass


class LLMClient:
    def __init__(self, cfg):
        self.cfg = cfg
        cfg.validate()
        self._url = f"{cfg.base_url}/chat/completions"

    def chat(self, system, user):
        """调用 chat completions，返回 assistant 文本内容。失败按配置重试。"""
        payload = {
            "model": self.cfg.model,
            "temperature": self.cfg.temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.cfg.api_key}",
            "Content-Type": "application/json",
        }

        last_err = None
        for attempt in range(self.cfg.max_retries + 1):
            try:
                resp = requests.post(
                    self._url, json=payload, headers=headers,
                    timeout=self.cfg.timeout_s,
                )
                # 限流 / 服务端错误：退避重试
                if resp.status_code in (429, 500, 502, 503, 504):
                    raise LLMError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            except (requests.RequestException, LLMError, KeyError, ValueError) as e:
                last_err = e
                if attempt >= self.cfg.max_retries:
                    break
                backoff = (2 ** attempt) + random.uniform(0, 1)
                logger.warning(
                    f"LLM 调用失败({e})，{backoff:.1f}s 后重试 "
                    f"({attempt + 1}/{self.cfg.max_retries})"
                )
                time.sleep(backoff)
        raise LLMError(f"LLM 调用最终失败: {last_err}")
