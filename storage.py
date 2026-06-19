import json
import logging
from datetime import datetime

import duckdb

from analyzer import _strip_html

logger = logging.getLogger(__name__)


POSTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    post_id        BIGINT PRIMARY KEY,
    user_id        BIGINT,
    screen_name    VARCHAR,
    created_at     TIMESTAMP,
    created_at_ms  BIGINT,
    title          VARCHAR,
    text           VARCHAR,      -- 清洗后的纯文本
    description    VARCHAR,      -- 原始 HTML 内容
    target         VARCHAR,
    url            VARCHAR,
    source         VARCHAR,
    is_column      BOOLEAN,
    reply_count    INTEGER,
    retweet_count  INTEGER,
    like_count     INTEGER,
    fav_count      INTEGER,
    view_count     INTEGER,
    retweeted_post_id  BIGINT,   -- 被转发原帖 id，可自关联 posts.post_id
    retweeted_user_id  BIGINT,   -- 被转发原帖作者 id
    crawled_at     TIMESTAMP,
    raw_json       VARCHAR
);
"""

USERS_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id          BIGINT PRIMARY KEY,
    screen_name      VARCHAR,
    followers_count  INTEGER,
    post_count       INTEGER,
    last_crawled_at  TIMESTAMP,
    resume_page      INTEGER,    -- 断点续爬：下次应从第几页继续
    last_status      VARCHAR     -- 'completed'（已抓完）| 'blocked'（中途被拦截）
);
"""

_POST_COLUMNS = [
    "post_id", "user_id", "screen_name", "created_at", "created_at_ms",
    "title", "text", "description", "target", "url", "source", "is_column",
    "reply_count", "retweet_count", "like_count", "fav_count", "view_count",
    "retweeted_post_id", "retweeted_user_id",
    "crawled_at", "raw_json",
]


def _ms_to_dt(ms):
    if not ms:
        return None
    try:
        return datetime.fromtimestamp(ms / 1000)
    except (ValueError, OSError):
        return None


def _to_int(value):
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


class PostStore:
    """将雪球帖子数据持久化到 DuckDB，按 post_id 幂等去重"""

    def __init__(self, db_path):
        self.db_path = db_path
        self._con = duckdb.connect(db_path)
        self._con.execute(POSTS_SCHEMA)
        self._con.execute(USERS_SCHEMA)
        # 兼容早期库：为缺失的新列做迁移
        for col in ("retweeted_post_id", "retweeted_user_id"):
            self._con.execute(f"ALTER TABLE posts ADD COLUMN IF NOT EXISTS {col} BIGINT")
        self._con.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS resume_page INTEGER")
        self._con.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_status VARCHAR")

    def _post_to_row(self, post, user_id=None, screen_name=None, crawled_at=None):
        user = post.get("user") or {}
        created_ms = post.get("created_at")
        target = post.get("target", "") or ""
        url = f"https://xueqiu.com{target}" if target.startswith("/") else target
        rt = post.get("retweeted_status") or {}
        rt_user = rt.get("user") or {}
        return [
            _to_int(post.get("id")),
            _to_int(post.get("user_id") or user.get("id") or user_id),
            user.get("screen_name") or screen_name or "",
            _ms_to_dt(created_ms),
            _to_int(created_ms),
            post.get("title") or "",
            _strip_html(post.get("text") or "") or _strip_html(post.get("description") or ""),
            post.get("description") or "",
            target,
            url,
            post.get("source") or "",
            bool(post.get("is_column")),
            _to_int(post.get("reply_count")),
            _to_int(post.get("retweet_count")),
            _to_int(post.get("like_count")),
            _to_int(post.get("fav_count")),
            _to_int(post.get("view_count")),
            _to_int(rt.get("id")) if rt else None,
            _to_int(rt.get("user_id") or rt_user.get("id")) if rt else None,
            crawled_at,
            json.dumps(post, ensure_ascii=False),
        ]

    @staticmethod
    def _expand_with_retweets(posts):
        """展开帖子及其被转发的原帖（含多层嵌套），按 id 去重后返回列表"""
        seen = {}

        def visit(p):
            if not isinstance(p, dict):
                return
            pid = p.get("id")
            if pid is None or pid in seen:
                return
            seen[pid] = p
            visit(p.get("retweeted_status"))

        for p in posts:
            visit(p)
        return list(seen.values())

    def save_posts(self, posts, user_id=None, screen_name=None):
        """批量写入帖子（含被转发原帖），已存在的 post_id 会被覆盖更新。返回写入条数"""
        crawled_at = datetime.now()
        expanded = self._expand_with_retweets(posts)
        rows = [
            self._post_to_row(p, user_id, screen_name, crawled_at)
            for p in expanded
        ]
        if not rows:
            return 0

        placeholders = ", ".join(["?"] * len(_POST_COLUMNS))
        sql = (
            f"INSERT OR REPLACE INTO posts ({', '.join(_POST_COLUMNS)}) "
            f"VALUES ({placeholders})"
        )
        self._con.executemany(sql, rows)
        extra = len(rows) - sum(1 for p in posts if isinstance(p, dict) and p.get("id") is not None)
        suffix = f"（含 {extra} 条被转发原帖）" if extra > 0 else ""
        logger.info(f"已写入 DuckDB: {len(rows)} 条帖子{suffix} -> {self.db_path}")
        return len(rows)

    def save_user(self, user_id, screen_name, followers_count=None, post_count=None):
        """记录/更新用户信息（不影响断点续爬状态字段）"""
        self._con.execute(
            """INSERT INTO users
                   (user_id, screen_name, followers_count, post_count, last_crawled_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT (user_id) DO UPDATE SET
                   screen_name = excluded.screen_name,
                   followers_count = coalesce(excluded.followers_count, users.followers_count),
                   post_count = excluded.post_count,
                   last_crawled_at = excluded.last_crawled_at""",
            [_to_int(user_id), screen_name, _to_int(followers_count),
             _to_int(post_count), datetime.now()],
        )

    def set_crawl_state(self, user_id, resume_page, completed):
        """记录断点续爬状态：completed 时清空续爬页，否则保存中断页"""
        status = "completed" if completed else "blocked"
        page = None if completed else _to_int(resume_page)
        self._con.execute(
            """INSERT INTO users (user_id, resume_page, last_status, last_crawled_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT (user_id) DO UPDATE SET
                   resume_page = excluded.resume_page,
                   last_status = excluded.last_status,
                   last_crawled_at = excluded.last_crawled_at""",
            [_to_int(user_id), page, status, datetime.now()],
        )

    def get_resume_page(self, user_id):
        """返回断点续爬的起始页：上次被拦截则从中断页继续，否则从第 1 页"""
        row = self._con.execute(
            "SELECT resume_page, last_status FROM users WHERE user_id = ?",
            [_to_int(user_id)],
        ).fetchone()
        if row and row[1] == "blocked" and row[0] and row[0] > 1:
            return int(row[0])
        return 1

    def dedup(self):
        """按 post_id 去重，保留最近抓取的一条，返回删除条数。

        正常写入已通过主键 + INSERT OR REPLACE 自动去重；
        此方法用于清理早期可能无主键/含重复的历史数据，可安全反复执行。
        """
        before = self.count_posts()
        self._con.execute(
            "DELETE FROM posts WHERE rowid NOT IN "
            "(SELECT max(rowid) FROM posts GROUP BY post_id)"
        )
        after = self.count_posts()
        removed = before - after
        if removed:
            logger.info(f"去重完成：删除 {removed} 条重复记录（{before} -> {after}）")
        else:
            logger.info(f"无重复记录（共 {after} 条）")
        return removed

    def count_posts(self, user_id=None):
        if user_id is not None:
            r = self._con.execute(
                "SELECT count(*) FROM posts WHERE user_id = ?", [_to_int(user_id)]
            ).fetchone()
        else:
            r = self._con.execute("SELECT count(*) FROM posts").fetchone()
        return r[0] if r else 0

    def close(self):
        try:
            self._con.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
