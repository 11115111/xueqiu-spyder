"""OpenAI 兼容的 Chat Completions 客户端。

厂商差异只在这一层：换厂商只改配置（base_url / key / model）。
裸 HTTP 实现，仅依赖 requests，可对接任意 OpenAI 兼容端点。

限流策略：
- 客户端 RPM 限流（跨线程共享，平滑请求起始时刻）；
- 命中 429/5xx 时优先按服务端 Retry-After 退避，否则指数退避；
- 重试本身也受限流约束，避免雪上加霜。
"""
import time
import logging
import random
import threading
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone

import requests

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS = (429, 500, 502, 503, 504)


class LLMError(Exception):
    pass


class RateLimiter:
    """线程安全的 RPM 限流：保证相邻请求起始至少间隔 60/rpm 秒。rpm<=0 不限流。"""

    def __init__(self, rpm):
        self.interval = 60.0 / rpm if rpm and rpm > 0 else 0.0
        self._lock = threading.Lock()
        self._next = 0.0

    def acquire(self):
        if self.interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            wait = self._next - now
            if wait > 0:
                time.sleep(wait)
                now = time.monotonic()
            self._next = max(now, self._next) + self.interval


def _parse_retry_after(resp):
    """解析 Retry-After（秒数或 HTTP 日期），返回秒数 float 或 None。"""
    val = resp.headers.get("Retry-After")
    if not val:
        return None
    val = val.strip()
    if val.isdigit():
        return float(val)
    try:
        dt = parsedate_to_datetime(val)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (dt - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError):
        return None


class LLMClient:
    def __init__(self, cfg, limiter=None):
        self.cfg = cfg
        cfg.validate()
        self._url = f"{cfg.base_url}/chat/completions"
        self._limiter = limiter or RateLimiter(getattr(cfg, "rpm", 0))

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
            self._limiter.acquire()  # 重试也受限流约束
            retry_after = None
            try:
                resp = requests.post(
                    self._url, json=payload, headers=headers,
                    timeout=self.cfg.timeout_s,
                )
                if resp.status_code in _RETRYABLE_STATUS:
                    retry_after = _parse_retry_after(resp)
                    raise LLMError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            except (requests.RequestException, LLMError, KeyError, ValueError) as e:
                last_err = e
                if attempt >= self.cfg.max_retries:
                    break
                # 优先服务端 Retry-After，否则指数退避 + 抖动
                backoff = retry_after if retry_after is not None else (2 ** attempt) + random.uniform(0, 1)
                logger.warning(
                    f"LLM 调用失败({e})，{backoff:.1f}s 后重试 "
                    f"({attempt + 1}/{self.cfg.max_retries})"
                    + ("（按 Retry-After）" if retry_after is not None else "")
                )
                time.sleep(backoff)
        raise LLMError(f"LLM 调用最终失败: {last_err}")
