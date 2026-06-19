"""复核队列导出 + 按概念/标的/正反例查询脚手架。"""
import os
import logging

from .store import ExtractStore

logger = logging.getLogger(__name__)


def _rows(con, where, params=None):
    sql = f"""
        SELECT c.post_id, c.behavior_summary, c.concepts, c.targets, c.cycle,
               c.polarity, c.polarity_confidence, c.key_quote, c.judgment,
               c.needs_review, c.source_post_date,
               'https://xueqiu.com' || coalesce(p.target, '') AS url
        FROM cards c
        LEFT JOIN posts p ON c.post_id = p.post_id
        WHERE {where}
        ORDER BY c.post_id, c.card_idx
    """
    return con.execute(sql, params or []).fetchall()


def query(db_path, concept=None, target=None, polarity=None, needs_review=False, limit=None):
    """组合查询卡片，返回行列表。"""
    with ExtractStore(db_path) as store:
        conds, params = [], []
        if concept:
            conds.append("list_contains(c.concepts, ?)"); params.append(concept)
        if target:
            conds.append("list_contains(c.targets, ?)"); params.append(target)
        if polarity:
            conds.append("c.polarity = ?"); params.append(polarity)
        if needs_review:
            conds.append("c.needs_review = true")
        where = " AND ".join(conds) if conds else "1=1"
        rows = _rows(store.con(), where, params)
    if limit:
        rows = rows[:limit]
    return rows


def export_review(db_path, out_path, concept=None, target=None, polarity=None,
                  needs_review=True):
    """把（默认待复核的）卡片导出为 Markdown 对照表，供人工校准。"""
    rows = query(db_path, concept=concept, target=target, polarity=polarity,
                 needs_review=needs_review)
    lines = [
        "# 抽取复核队列" if needs_review else "# 抽取卡片查询结果",
        "",
        f"> 共 {len(rows)} 张卡",
        "",
        "| post_id | 概念 | 标的 | 周期 | 正反例 | 置信 | key_quote | 复述 | 链接 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        (post_id, summary, concepts, targets, cycle, pol, conf,
         quote, _judg, _nr, _spd, url) = r
        def cell(x):
            return str(x or "").replace("|", "/").replace("\n", " ")
        lines.append(
            f"| {post_id} | {cell('、'.join(concepts or []))} | "
            f"{cell('、'.join(targets or []))} | {cell(cycle)} | {cell(pol)} | "
            f"{cell(conf)} | {cell(quote)} | {cell(summary)} | {cell(url)} |"
        )
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    logger.info(f"已导出 {len(rows)} 张卡到 {out_path}")
    return out_path
