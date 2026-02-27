import os
from datetime import datetime

import config


def generate_report(symbol, users_opinions, output_dir=None):
    """生成 Markdown 格式的大V观点汇总报告"""
    if output_dir is None:
        output_dir = config.DEFAULT_OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"# {symbol} 大V观点汇总",
        "",
        f"> 生成时间: {timestamp}  ",
        f"> 筛选条件: 评论数 > {config.MIN_REPLY_COUNT}  ",
        f"> 共发现 {len(users_opinions)} 位大V",
        "",
        "---",
        "",
    ]

    for idx, (user_info, opinions) in enumerate(users_opinions, 1):
        lines.append(f"## {idx}. {user_info.screen_name}")
        lines.append("")
        lines.append(f"- 粉丝数: {user_info.followers_count}")
        lines.append(f"- 相关帖子数: {len(opinions)}")
        lines.append("")

        if opinions:
            lines.append("### 核心观点")
            lines.append("")
            for op in opinions[:3]:
                text = op.text[:200] + "..." if len(op.text) > 200 else op.text
                lines.append(f"- {text}")
            lines.append("")

            lines.append("### 热门帖子")
            lines.append("")
            lines.append("| 时间 | 内容摘要 | 评论 | 点赞 |")
            lines.append("|------|----------|------|------|")
            for op in opinions:
                short = op.text[:80].replace("|", "/").replace("\n", " ")
                if len(op.text) > 80:
                    short += "..."
                lines.append(f"| {op.created_at} | {short} | {op.reply_count} | {op.like_count} |")
            lines.append("")

        lines.append("---")
        lines.append("")

    filename = f"{symbol}_大V观点_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return filepath


def generate_user_report(screen_name, user_id, opinions, output_dir=None):
    """生成某位用户的帖子汇总报告"""
    if output_dir is None:
        output_dir = config.DEFAULT_OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"# {screen_name} 帖子汇总",
        "",
        f"> 生成时间: {timestamp}  ",
        f"> 用户ID: {user_id}  ",
        f"> 共 {len(opinions)} 条帖子",
        "",
        "---",
        "",
    ]

    # 按股票分组统计
    stock_counts = {}
    for op in opinions:
        for match in __import__("re").findall(r"\$([^$]+)\$", op.text):
            stock_counts[match] = stock_counts.get(match, 0) + 1
    if stock_counts:
        lines.append("## 关注股票")
        lines.append("")
        for stock, cnt in sorted(stock_counts.items(), key=lambda x: -x[1])[:10]:
            lines.append(f"- {stock}: {cnt} 次提及")
        lines.append("")
        lines.append("---")
        lines.append("")

    lines.append("## 热门帖子")
    lines.append("")
    lines.append("| 时间 | 内容摘要 | 评论 | 点赞 |")
    lines.append("|------|----------|------|------|")
    for op in opinions:
        short = op.text[:80].replace("|", "/").replace("\n", " ")
        if len(op.text) > 80:
            short += "..."
        lines.append(f"| {op.created_at} | {short} | {op.reply_count} | {op.like_count} |")
    lines.append("")
    lines.append("---")
    lines.append("")

    lines.append("## 帖子详情")
    lines.append("")
    for idx, op in enumerate(opinions, 1):
        lines.append(f"### {idx}. [{op.created_at}] 评论:{op.reply_count} 点赞:{op.like_count}")
        lines.append("")
        lines.append(op.text)
        lines.append("")

    filename = f"用户_{screen_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return filepath
