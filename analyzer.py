import re
import logging
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class UserInfo:
    user_id: int
    screen_name: str
    followers_count: int
    post_ids: list = field(default_factory=list)


@dataclass
class Opinion:
    post_id: int
    text: str
    reply_count: int
    like_count: int
    created_at: str


def _strip_html(text):
    """去除 HTML 标签，保留纯文本"""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\$([^$]+)\$", r"\1", text)  # 去掉 $股票名(代码)$ 格式
    # 去掉详情页自带的来源前缀
    text = re.sub(r"^来源：雪球App，作者：[^）]+）", "", text)
    return text.strip()


def _parse_timestamp(ts):
    """将毫秒时间戳转为可读字符串"""
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M")
    except (ValueError, OSError):
        return str(ts)


def filter_big_v(posts, min_reply_count):
    """从帖子列表中筛选大V用户（评论数超过阈值）"""
    big_v_map = {}
    for post in posts:
        reply_count = post.get("reply_count", 0)
        if reply_count < min_reply_count:
            continue
        user = post.get("user", {})
        uid = user.get("id") or post.get("user_id")
        if not uid:
            continue
        if uid not in big_v_map:
            big_v_map[uid] = UserInfo(
                user_id=uid,
                screen_name=user.get("screen_name", "未知"),
                followers_count=user.get("followers_count", 0),
                post_ids=[post["id"]],
            )
        else:
            big_v_map[uid].post_ids.append(post["id"])

    logger.info(f"筛选出 {len(big_v_map)} 位大V")
    return big_v_map


def extract_opinions(posts, symbol):
    """从用户帖子中提取与目标股票相关的观点"""
    opinions = []
    symbol_upper = symbol.upper()
    for post in posts:
        # 检查帖子是否与目标股票相关（在原始 HTML 内容中搜索）
        text = post.get("text", "") or ""
        desc = post.get("description", "") or ""
        title = post.get("title", "") or ""
        raw_content = f"{text} {desc} {title}".upper()
        if symbol_upper not in raw_content:
            continue

        clean_text = _strip_html(text)
        if not clean_text:
            clean_text = _strip_html(desc)
        if not clean_text:
            continue

        opinions.append(Opinion(
            post_id=post.get("id", 0),
            text=clean_text,
            reply_count=post.get("reply_count", 0),
            like_count=post.get("like_count", 0),
            created_at=_parse_timestamp(post.get("created_at")),
        ))

    return opinions


def summarize_opinions(opinions, top_n=5):
    """按互动量排序，取 Top N 条作为核心观点摘要"""
    if not opinions:
        return []
    ranked = sorted(
        opinions,
        key=lambda o: o.reply_count * 2 + o.like_count,
        reverse=True,
    )
    return ranked[:top_n]


def posts_to_opinions(posts):
    """将原始帖子列表转为 Opinion 列表（不做股票过滤）"""
    opinions = []
    for post in posts:
        text = post.get("text", "") or ""
        desc = post.get("description", "") or ""
        clean_text = _strip_html(text)
        if not clean_text:
            clean_text = _strip_html(desc)
        if not clean_text:
            continue
        opinions.append(Opinion(
            post_id=post.get("id", 0),
            text=clean_text,
            reply_count=post.get("reply_count", 0),
            like_count=post.get("like_count", 0),
            created_at=_parse_timestamp(post.get("created_at")),
        ))
    return opinions
