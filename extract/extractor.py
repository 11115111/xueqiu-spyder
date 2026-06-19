"""单条帖抽取：拼 prompt -> 调 LLM -> 解析 -> 校验归一 -> 返回 cards[]。"""
import re
import json
import logging

from .prompt import build_user_message, CARD_FIELDS

logger = logging.getLogger(__name__)

UNCLASSIFIED = "未分类"
DEFAULT_CYCLE = "待定"

_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


class ParseError(Exception):
    pass


def parse_json_array(raw):
    """剥离 ```json 围栏后 json.loads，必须得到一个数组。"""
    if raw is None:
        raise ParseError("空响应")
    text = raw.strip()
    text = _FENCE_RE.sub("", text).strip()
    # 容错：截取第一个 [ 到最后一个 ] 之间
    if not text.startswith("["):
        l, r = text.find("["), text.rfind("]")
        if l != -1 and r != -1 and r > l:
            text = text[l:r + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ParseError(f"JSON 解析失败: {e}")
    if not isinstance(data, list):
        raise ParseError("顶层不是 JSON 数组")
    return data


def _as_list(v):
    if v is None:
        return []
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    s = str(v).strip()
    return [s] if s else []


def normalize_card(obj, taxonomy):
    """补全字段、归一枚举；返回 (card_dict, normalized_bool)。

    非枚举概念 → "未分类" 且 needs_review=true；非枚举 cycle → "待定"。
    """
    if not isinstance(obj, dict):
        obj = {}
    card = {f: obj.get(f) for f in CARD_FIELDS}

    valid_concepts = set(taxonomy.concept_names) | {UNCLASSIFIED}
    concepts = _as_list(card.get("concepts"))
    forced_review = False
    if concepts:
        kept = [c for c in concepts if c in valid_concepts]
        if len(kept) != len(concepts):
            forced_review = True  # 出现非枚举概念
        concepts = kept or [UNCLASSIFIED]
    else:
        concepts = [UNCLASSIFIED]
    if UNCLASSIFIED in concepts:
        forced_review = True
    card["concepts"] = concepts

    card["targets"] = _as_list(card.get("targets"))

    cycle = (card.get("cycle") or "").strip()
    if cycle not in set(taxonomy.cycles):
        cycle = DEFAULT_CYCLE
    card["cycle"] = cycle

    polarity = (card.get("polarity") or "").strip()
    if polarity not in set(taxonomy.polarities):
        polarity = "不适用"
    card["polarity"] = polarity

    conf = (card.get("polarity_confidence") or "").strip().lower()
    if conf not in set(taxonomy.confidences):
        conf = "low"
        forced_review = True
    card["polarity_confidence"] = conf

    # 文本字段归一为字符串，空 → ""；可空字段保持 None
    for f in ("behavior_summary", "polarity_reason", "scene", "judgment", "judgment_basis"):
        card[f] = (str(card.get(f)).strip() if card.get(f) is not None else "")
    for f in ("date", "key_quote", "verification", "error_type"):
        v = card.get(f)
        card[f] = (str(v).strip() if v not in (None, "") else None)

    nr = card.get("needs_review")
    nr = bool(nr) if isinstance(nr, bool) else str(nr).strip().lower() in ("true", "1", "yes")
    card["needs_review"] = nr or conf == "low" or forced_review

    return card


def extract_post(post, llm, system_prompt, taxonomy):
    """对单条帖抽取，返回归一后的 cards 列表。文本为空直接返回 []。"""
    text = (post.get("text") or "").strip()
    if not text:
        return []
    user = build_user_message(post["post_id"], post.get("post_date"), text)
    raw = llm.chat(system_prompt, user)
    try:
        arr = parse_json_array(raw)
    except ParseError as e:
        e.raw = raw  # 供 runner 落 failed 表时记录原始响应
        raise
    return [normalize_card(o, taxonomy) for o in arr]
