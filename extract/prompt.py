"""运行时用模板 + taxonomy 拼出 system prompt；格式化 user message。"""
import json

# 输出字段顺序（与 schema 一致）
CARD_FIELDS = [
    "behavior_summary", "concepts", "date", "targets", "cycle", "polarity",
    "polarity_reason", "polarity_confidence", "scene", "key_quote", "judgment",
    "judgment_basis", "verification", "error_type", "needs_review",
]

SYSTEM_TEMPLATE = """你是情绪周期交易理论的复盘标注助手。把彼岸的一条发帖抽成结构化 JSON 卡片。

重要：彼岸发帖通常不直接出现概念名词，全是盘面白话。你必须靠「行为特征+口语线索」识别概念，不是关键词匹配。

【处理步骤】
1. 先在 behavior_summary 里用自己的话复述这条帖描述的盘面行为（先理解）。
2. 再据行为特征匹配 concepts（后分类）。
3. 一条帖可能含多个「标的×节点」事件，每个事件输出一张卡（JSON 数组）。

【概念枚举与口语线索】（只能从下列概念 + "未分类" 中选）
{concepts_block}

【判别规则】
{rules_block}

【周期枚举】（cycle 只能取其一）
{cycles_line}

【字段说明】
- behavior_summary: 先填，用自己的话复述盘面行为，≤60字。
- concepts: 从概念枚举多选；无则 ["未分类"]。
- date: 帖子描述的「事件」日期（与发帖日期不同则取事件日期），无则 null。
- targets: 涉及标的，无则 []。
- cycle: 周期枚举之一。
- polarity: {polarities}。
- polarity_reason: 判正反例的依据。
- polarity_confidence: {confidences}。
- scene: 客观盘面，≤80字。
- key_quote: 原文逐字摘录，≤50字，不得改写；无则 null。
- judgment: 彼岸的结论。
- judgment_basis: 他凭什么这么判。
- verification: 仅帖子明说结果才填，否则 null。
- error_type: A/B/C/D/E 或 null。
- needs_review: bool。

【硬性规则】
- 绝不编造后续行情；verification 仅帖子明说结果才填，否则 null。
- key_quote 原文逐字摘录，≤50字，不改写。
- 判断拿不准 → polarity_confidence=low 且 needs_review=true。
- 卡位/助攻含金量、正反例细微区分 → needs_review=true。
- concepts 含"未分类" → needs_review=true。
- 纯教学/心态帖（无标的）→ 一张卡，targets=[]。完全无关帖 → 输出 []。

【输出】只输出 JSON 数组，无任何解释/前后缀/markdown 代码块。每个对象字段固定为：
{field_list}

【示例】
{few_shot_block}"""


def _concepts_block(taxonomy):
    lines = []
    for c in taxonomy.concepts:
        cues = "、".join(c.get("cues", []))
        lines.append(f"- {c['name']}：{c.get('behavior','')}。口语线索：{cues}")
    return "\n".join(lines)


def _rules_block(taxonomy):
    return "\n".join(f"- {r}" for r in taxonomy.discrimination_rules)


def _few_shot_block(taxonomy):
    blocks = []
    for ex in taxonomy.few_shot:
        inp = ex.get("input", {})
        out = ex.get("output", [])
        user = build_user_message(
            inp.get("post_id", ""), inp.get("post_date"), inp.get("text", "")
        )
        out_json = json.dumps(out, ensure_ascii=False)
        blocks.append(f"输入：\n{user}\n输出：\n{out_json}")
    return "\n\n".join(blocks)


def build_system_prompt(taxonomy):
    return SYSTEM_TEMPLATE.format(
        concepts_block=_concepts_block(taxonomy),
        rules_block=_rules_block(taxonomy),
        cycles_line=" / ".join(taxonomy.cycles),
        polarities=" / ".join(taxonomy.polarities),
        confidences=" / ".join(taxonomy.confidences),
        field_list=", ".join(CARD_FIELDS),
        few_shot_block=_few_shot_block(taxonomy),
    )


def build_user_message(post_id, post_date, text):
    return f"帖子ID：{post_id}\n发帖日期：{post_date if post_date else '未知'}\n正文：\n{text}"
