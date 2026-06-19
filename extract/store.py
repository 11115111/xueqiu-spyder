"""存储适配层：复用发帖所在的 DuckDB，抽取结果写到并列的新表。

读：posts 表（爬虫已写入）。
写：cards / failed / extract_status，与原发帖表同库并列，不改动原表。
"""
import logging
from datetime import datetime

import duckdb

logger = logging.getLogger(__name__)

CARDS_SCHEMA = """
CREATE TABLE IF NOT EXISTS cards (
    post_id              BIGINT,
    card_idx             INTEGER,
    behavior_summary     VARCHAR,
    concepts             VARCHAR[],
    event_date           VARCHAR,
    targets              VARCHAR[],
    cycle                VARCHAR,
    polarity             VARCHAR,
    polarity_reason      VARCHAR,
    polarity_confidence  VARCHAR,
    scene                VARCHAR,
    key_quote            VARCHAR,
    judgment             VARCHAR,
    judgment_basis       VARCHAR,
    verification         VARCHAR,
    error_type           VARCHAR,
    needs_review         BOOLEAN,
    source_post_date     VARCHAR,
    model                VARCHAR,
    run_at               TIMESTAMP,
    PRIMARY KEY (post_id, card_idx)
);
"""

FAILED_SCHEMA = """
CREATE TABLE IF NOT EXISTS failed (
    post_id  BIGINT,
    err      VARCHAR,
    raw      VARCHAR,
    ts       TIMESTAMP
);
"""

STATUS_SCHEMA = """
CREATE TABLE IF NOT EXISTS extract_status (
    post_id     BIGINT PRIMARY KEY,
    status      VARCHAR,   -- pending / done / failed
    n_cards     INTEGER,
    updated_at  TIMESTAMP
);
"""

# cards 列顺序（card 字段 + 元数据），event_date 对应 schema 的 date
_CARD_COLS = [
    "post_id", "card_idx", "behavior_summary", "concepts", "event_date", "targets",
    "cycle", "polarity", "polarity_reason", "polarity_confidence", "scene",
    "key_quote", "judgment", "judgment_basis", "verification", "error_type",
    "needs_review", "source_post_date", "model", "run_at",
]


class ExtractStore:
    def __init__(self, db_path):
        self.db_path = db_path
        self._con = duckdb.connect(db_path)
        self._con.execute(CARDS_SCHEMA)
        self._con.execute(FAILED_SCHEMA)
        self._con.execute(STATUS_SCHEMA)

    # ---- 读发帖 ----
    def iter_posts(self, mode="todo", limit=None):
        """生成待处理帖子：{post_id, post_date, text}。

        mode: 'todo'=未完成(无状态/pending/failed) | 'failed'=仅失败 | 'all'=全部
        """
        where = {
            "todo": "s.status IS NULL OR s.status IN ('pending','failed')",
            "failed": "s.status = 'failed'",
            "all": "1=1",
        }[mode]
        sql = f"""
            SELECT p.post_id,
                   strftime(p.created_at, '%Y-%m-%d') AS post_date,
                   trim(coalesce(p.title,'') || '\n' || coalesce(p.text,'')) AS text
            FROM posts p
            LEFT JOIN extract_status s ON p.post_id = s.post_id
            WHERE {where}
            ORDER BY p.created_at DESC NULLS LAST
        """
        if limit:
            sql += f" LIMIT {int(limit)}"
        for row in self._con.execute(sql).fetchall():
            yield {"post_id": row[0], "post_date": row[1], "text": row[2]}

    def count_todo(self, mode="todo"):
        return sum(1 for _ in self.iter_posts(mode=mode))

    # ---- 写抽取结果 ----
    def upsert_cards(self, post_id, cards, model="", source_post_date=None):
        """先删该 post_id 旧卡再插，保证幂等。"""
        run_at = datetime.now()
        self._con.execute("DELETE FROM cards WHERE post_id = ?", [post_id])
        if not cards:
            return 0
        rows = []
        for idx, c in enumerate(cards):
            rows.append([
                post_id, idx,
                c.get("behavior_summary", ""),
                c.get("concepts", []),
                c.get("date"),
                c.get("targets", []),
                c.get("cycle", ""),
                c.get("polarity", ""),
                c.get("polarity_reason", ""),
                c.get("polarity_confidence", ""),
                c.get("scene", ""),
                c.get("key_quote"),
                c.get("judgment", ""),
                c.get("judgment_basis", ""),
                c.get("verification"),
                c.get("error_type"),
                bool(c.get("needs_review")),
                source_post_date,
                model,
                run_at,
            ])
        placeholders = ", ".join(["?"] * len(_CARD_COLS))
        self._con.executemany(
            f"INSERT INTO cards ({', '.join(_CARD_COLS)}) VALUES ({placeholders})",
            rows,
        )
        return len(rows)

    def mark_status(self, post_id, status, n_cards=None):
        self._con.execute(
            """INSERT INTO extract_status (post_id, status, n_cards, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT (post_id) DO UPDATE SET
                   status = excluded.status,
                   n_cards = excluded.n_cards,
                   updated_at = excluded.updated_at""",
            [post_id, status, n_cards, datetime.now()],
        )

    def log_failed(self, post_id, err, raw=None):
        self._con.execute(
            "INSERT INTO failed (post_id, err, raw, ts) VALUES (?, ?, ?, ?)",
            [post_id, str(err)[:2000], (raw or "")[:4000] or None, datetime.now()],
        )

    def con(self):
        return self._con

    def close(self):
        try:
            self._con.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
