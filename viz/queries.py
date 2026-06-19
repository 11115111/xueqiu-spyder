"""仪表盘的数据查询层：纯 SQL -> DataFrame，不依赖 streamlit，便于单测。

围绕 cards 表（情绪周期结构化卡片）做聚合；按需 LEFT JOIN posts 取原帖链接。
"""
import duckdb


def connect(db_path, read_only=True):
    return duckdb.connect(db_path, read_only=read_only)


def has_cards(con):
    rows = con.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_name = 'cards'"
    ).fetchone()
    return bool(rows and rows[0])


def filter_options(con):
    """各筛选维度的可选值。"""
    def col(sql):
        return [r[0] for r in con.execute(sql).fetchall() if r[0] not in (None, "")]
    concepts = col("SELECT DISTINCT unnest(concepts) c FROM cards ORDER BY c")
    targets = col("SELECT DISTINCT unnest(targets) t FROM cards ORDER BY t")
    cycles = col("SELECT DISTINCT cycle FROM cards ORDER BY cycle")
    polarities = col("SELECT DISTINCT polarity FROM cards ORDER BY polarity")
    confidences = col("SELECT DISTINCT polarity_confidence FROM cards ORDER BY polarity_confidence")
    dates = con.execute(
        "SELECT min(source_post_date), max(source_post_date) FROM cards "
        "WHERE source_post_date IS NOT NULL"
    ).fetchone()
    return {
        "concepts": concepts, "targets": targets, "cycles": cycles,
        "polarities": polarities, "confidences": confidences,
        "date_min": dates[0] if dates else None,
        "date_max": dates[1] if dates else None,
    }


def build_where(f):
    """根据筛选条件拼 WHERE 子句与参数。f 为 dict。"""
    conds, params = ["1=1"], []
    f = f or {}
    if f.get("cycles"):
        conds.append(f"cycle IN ({','.join(['?'] * len(f['cycles']))})")
        params += list(f["cycles"])
    if f.get("polarities"):
        conds.append(f"polarity IN ({','.join(['?'] * len(f['polarities']))})")
        params += list(f["polarities"])
    if f.get("confidences"):
        conds.append(f"polarity_confidence IN ({','.join(['?'] * len(f['confidences']))})")
        params += list(f["confidences"])
    if f.get("concepts"):
        conds.append("list_has_any(concepts, ?)")
        params.append(list(f["concepts"]))
    if f.get("targets"):
        conds.append("list_has_any(targets, ?)")
        params.append(list(f["targets"]))
    if f.get("needs_review"):
        conds.append("needs_review = true")
    if f.get("date_from"):
        conds.append("source_post_date >= ?")
        params.append(str(f["date_from"]))
    if f.get("date_to"):
        conds.append("source_post_date <= ?")
        params.append(str(f["date_to"]))
    return " AND ".join(conds), params


def _df(con, sql, params):
    return con.execute(sql, params).df()


def kpis(con, f):
    where, p = build_where(f)
    row = con.execute(f"""
        SELECT count(*) AS cards,
               count(DISTINCT post_id) AS posts,
               count(*) FILTER (WHERE needs_review) AS review,
               count(*) FILTER (WHERE polarity = '正例') AS pos,
               count(*) FILTER (WHERE polarity = '反例') AS neg
        FROM cards WHERE {where}
    """, p).fetchone()
    keys = ["cards", "posts", "review", "pos", "neg"]
    return dict(zip(keys, row)) if row else {k: 0 for k in keys}


def concept_counts(con, f):
    where, p = build_where(f)
    return _df(con, f"""
        SELECT concept, count(*) AS n
        FROM (SELECT unnest(concepts) AS concept FROM cards WHERE {where})
        GROUP BY 1 ORDER BY n DESC
    """, p)


def polarity_by_concept(con, f):
    where, p = build_where(f)
    return _df(con, f"""
        SELECT concept, polarity, count(*) AS n
        FROM (SELECT unnest(concepts) AS concept, polarity FROM cards WHERE {where})
        GROUP BY 1, 2 ORDER BY concept
    """, p)


def cycle_counts(con, f):
    where, p = build_where(f)
    return _df(con, f"SELECT cycle, count(*) AS n FROM cards WHERE {where} GROUP BY 1 ORDER BY n DESC", p)


def target_counts(con, f, limit=30):
    where, p = build_where(f)
    return _df(con, f"""
        SELECT target, count(*) AS n
        FROM (SELECT unnest(targets) AS target FROM cards WHERE {where})
        GROUP BY 1 ORDER BY n DESC LIMIT {int(limit)}
    """, p)


def confidence_counts(con, f):
    where, p = build_where(f)
    return _df(con, f"""
        SELECT polarity_confidence AS confidence, count(*) AS n
        FROM cards WHERE {where} GROUP BY 1 ORDER BY n DESC
    """, p)


def timeline(con, f):
    where, p = build_where(f)
    return _df(con, f"""
        SELECT source_post_date AS date, polarity, count(*) AS n
        FROM cards WHERE {where} AND source_post_date IS NOT NULL
        GROUP BY 1, 2 ORDER BY 1
    """, p)


def card_table(con, f, limit=500):
    where, p = build_where(f)
    return _df(con, f"""
        SELECT c.post_id, c.source_post_date AS post_date, c.concepts, c.targets,
               c.cycle, c.polarity, c.polarity_confidence AS confidence,
               c.key_quote, c.judgment, c.needs_review,
               'https://xueqiu.com' || coalesce(p.target, '') AS url
        FROM cards c LEFT JOIN posts p ON c.post_id = p.post_id
        WHERE {where}
        ORDER BY c.source_post_date DESC NULLS LAST, c.post_id
        LIMIT {int(limit)}
    """, p)
