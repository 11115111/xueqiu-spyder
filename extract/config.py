"""配置：环境变量（第三方 LLM，OpenAI 兼容）+ taxonomy.yaml 加载。

换 LLM 厂商只需改 env；改分类规则只改 taxonomy.yaml，均不动代码。
"""
import os
from dataclasses import dataclass, field

import yaml

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TAXONOMY = os.path.join(_HERE, "taxonomy.yaml")
DEFAULT_LLM_CONFIG = os.path.join(_HERE, "llm.yaml")
# 复用爬虫的默认 DuckDB 路径（与发帖数据同库并列）
DEFAULT_DB = os.environ.get("XUEQIU_DB", "./xueqiu.duckdb")


def _env(name, default=None):
    v = os.environ.get(name)
    return v if v not in (None, "") else default


@dataclass
class LLMConfig:
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    temperature: float = 0.0
    concurrency: int = 5
    max_retries: int = 3
    timeout_s: int = 60
    rpm: int = 0   # 每分钟请求数上限（客户端限流），0 表示不限
    prompt_cache: str = "off"   # off | anthropic（给 system 注入 cache_control）

    @classmethod
    def load(cls, path=None):
        """从 YAML 配置文件读取 LLM 设置；同名环境变量优先级最高（便于把密钥放 env）。

        优先级：环境变量 > 配置文件 > 默认值。
        """
        path = path or DEFAULT_LLM_CONFIG
        data = {}
        if path and os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
            # 兼容两种写法：字段放在 llm: 下，或直接写在顶层
            data = raw.get("llm", raw) if isinstance(raw, dict) else {}

        def pick(key, env, cast, default):
            ev = _env(env)
            if ev is not None:
                return cast(ev)
            if key in data and data[key] not in (None, ""):
                return cast(data[key])
            return default

        return cls(
            base_url=(pick("base_url", "LLM_BASE_URL", str, "")).rstrip("/"),
            api_key=pick("api_key", "LLM_API_KEY", str, ""),
            model=pick("model", "LLM_MODEL", str, ""),
            temperature=pick("temperature", "LLM_TEMPERATURE", float, 0.0),
            concurrency=pick("concurrency", "LLM_CONCURRENCY", int, 5),
            max_retries=pick("max_retries", "LLM_MAX_RETRIES", int, 3),
            timeout_s=pick("timeout_s", "LLM_TIMEOUT_S", int, 60),
            rpm=pick("rpm", "LLM_RPM", int, 0),
            prompt_cache=pick("prompt_cache", "LLM_PROMPT_CACHE", str, "off"),
        )

    @classmethod
    def from_env(cls):
        """仅从环境变量读取（向后兼容）。"""
        return cls(
            base_url=(_env("LLM_BASE_URL", "") or "").rstrip("/"),
            api_key=_env("LLM_API_KEY", ""),
            model=_env("LLM_MODEL", ""),
            temperature=float(_env("LLM_TEMPERATURE", "0") or 0),
            concurrency=int(_env("LLM_CONCURRENCY", "5") or 5),
            max_retries=int(_env("LLM_MAX_RETRIES", "3") or 3),
            timeout_s=int(_env("LLM_TIMEOUT_S", "60") or 60),
            rpm=int(_env("LLM_RPM", "0") or 0),
            prompt_cache=_env("LLM_PROMPT_CACHE", "off"),
        )

    def validate(self):
        missing = [k for k in ("base_url", "api_key", "model") if not getattr(self, k)]
        if missing:
            raise ValueError(
                "缺少 LLM 配置: " + ", ".join(missing)
                + "。请在 extract/llm.yaml 中填写（参考 llm.yaml.example），"
                "或用环境变量 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL 覆盖。"
            )


@dataclass
class Taxonomy:
    concepts: list = field(default_factory=list)        # [{name, behavior, cues[]}]
    discrimination_rules: list = field(default_factory=list)
    cycles: list = field(default_factory=list)
    polarities: list = field(default_factory=list)
    confidences: list = field(default_factory=list)
    few_shot: list = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    @property
    def concept_names(self):
        return [c["name"] for c in self.concepts]

    @classmethod
    def load(cls, path=None):
        path = path or DEFAULT_TAXONOMY
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return cls(
            concepts=data.get("concepts", []),
            discrimination_rules=data.get("discrimination_rules", []),
            cycles=data.get("cycles", []),
            polarities=data.get("polarities", ["正例", "反例", "中性", "不适用"]),
            confidences=data.get("confidences", ["high", "medium", "low"]),
            few_shot=data.get("few_shot", []),
            raw=data,
        )
