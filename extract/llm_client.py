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
# prompt_cache 取这些值时，显式给 system 注入 cache_control（Anthropic 风格）
_CACHE_EXPLICIT = {"on", "anthropic", "explicit", "ephemeral", "true", "1"}


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
        self._stats_lock = threading.Lock()
        # 累计 token 用量，便于观察 prompt 缓存命中效果
        self.stats = {"calls": 0, "prompt_tokens": 0, "cached_tokens": 0,
                      "completion_tokens": 0}

    def _system_message(self, system):
        """构造 system 消息；显式开启缓存时给 system 注入 cache_control。

        长且稳定的 system prompt 作为可缓存前缀：OpenAI/DeepSeek 等会自动按前缀缓存
        （无需任何设置，off 也照样命中）；Anthropic 风格端点需显式 cache_control，
        故 prompt_cache 设为 on/anthropic 时注入。
        """
        if str(getattr(self.cfg, "prompt_cache", "off")).strip().lower() in _CACHE_EXPLICIT:
            return {
                "role": "system",
                "content": [
                    {"type": "text", "text": system,
                     "cache_control": {"type": "ephemeral"}}
                ],
            }
        return {"role": "system", "content": system}

    def _record_usage(self, data):
        usage = data.get("usage") or {}
        det = usage.get("prompt_tokens_details") or {}
        # 兼容各厂商的缓存命中字段：
        #   OpenAI: prompt_tokens_details.cached_tokens
        #   DeepSeek: prompt_cache_hit_tokens
        #   Anthropic: cache_read_input_tokens
        #   Gemini(OpenAI兼容): cached_content_token_count / 嵌套于 details
        cached = (det.get("cached_tokens")
                  or det.get("cached_content_token_count")
                  or usage.get("prompt_cache_hit_tokens")
                  or usage.get("cache_read_input_tokens")
                  or usage.get("cached_content_token_count") or 0)
        with self._stats_lock:
            self.stats["calls"] += 1
            self.stats["prompt_tokens"] += usage.get("prompt_tokens") or 0
            self.stats["completion_tokens"] += usage.get("completion_tokens") or 0
            self.stats["cached_tokens"] += cached or 0

    def chat(self, system, user):
        """调用 chat completions，返回 assistant 文本内容。失败按配置重试。"""
        payload = {
            "model": self.cfg.model,
            "temperature": self.cfg.temperature,
            "messages": [
                self._system_message(system),
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
                content = data["choices"][0]["message"]["content"]
                self._record_usage(data)
                return content
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
