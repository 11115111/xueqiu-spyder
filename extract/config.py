"""配置：环境变量（第三方 LLM，OpenAI 兼容）+ taxonomy.yaml 加载。

换 LLM 厂商只需改 env；改分类规则只改 taxonomy.yaml，均不动代码。
"""
import os
from dataclasses import dataclass, field

import yaml

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TAXONOMY = os.path.join(_HERE, "taxonomy.yaml")
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

    @classmethod
    def from_env(cls):
        return cls(
            base_url=(_env("LLM_BASE_URL", "") or "").rstrip("/"),
            api_key=_env("LLM_API_KEY", ""),
            model=_env("LLM_MODEL", ""),
            temperature=float(_env("LLM_TEMPERATURE", "0") or 0),
            concurrency=int(_env("LLM_CONCURRENCY", "5") or 5),
            max_retries=int(_env("LLM_MAX_RETRIES", "3") or 3),
            timeout_s=int(_env("LLM_TIMEOUT_S", "60") or 60),
        )

    def validate(self):
        missing = [k for k in ("base_url", "api_key", "model") if not getattr(self, k)]
        if missing:
            raise ValueError(
                "缺少 LLM 配置环境变量: "
                + ", ".join("LLM_" + m.upper() for m in missing)
                + "。请设置 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL。"
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
