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
    last_crawled_at  TIMESTAMP
);
"""

_POST_COLUMNS = [
    "post_id", "user_id", "screen_name", "created_at", "created_at_ms",
    "title", "text", "description", "target", "url", "source", "is_column",
    "reply_count", "retweet_count", "like_count", "fav_count", "view_count",
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

    def _post_to_row(self, post, user_id=None, screen_name=None, crawled_at=None):
        user = post.get("user") or {}
        created_ms = post.get("created_at")
        target = post.get("target", "") or ""
        url = f"https://xueqiu.com{target}" if target.startswith("/") else target
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
            crawled_at,
            json.dumps(post, ensure_ascii=False),
        ]

    def save_posts(self, posts, user_id=None, screen_name=None):
        """批量写入帖子，已存在的 post_id 会被覆盖更新。返回写入条数"""
        crawled_at = datetime.now()
        rows = [
            self._post_to_row(p, user_id, screen_name, crawled_at)
            for p in posts
            if p.get("id") is not None
        ]
        if not rows:
            return 0

        placeholders = ", ".join(["?"] * len(_POST_COLUMNS))
        sql = (
            f"INSERT OR REPLACE INTO posts ({', '.join(_POST_COLUMNS)}) "
            f"VALUES ({placeholders})"
        )
        self._con.executemany(sql, rows)
        logger.info(f"已写入 DuckDB: {len(rows)} 条帖子 -> {self.db_path}")
        return len(rows)

    def save_user(self, user_id, screen_name, followers_count=None, post_count=None):
        """记录/更新用户信息"""
        self._con.execute(
            """INSERT OR REPLACE INTO users
               (user_id, screen_name, followers_count, post_count, last_crawled_at)
               VALUES (?, ?, ?, ?, ?)""",
            [_to_int(user_id), screen_name, _to_int(followers_count),
             _to_int(post_count), datetime.now()],
        )

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
