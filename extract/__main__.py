"""命令行入口：python -m extract <run|review|stats> ...

不依赖 playwright/爬虫，可独立运行。
"""
import argparse
import logging
import sys

import duckdb

from .config import DEFAULT_DB, DEFAULT_TAXONOMY

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("extract")


def _cmd_run(args):
    from .runner import run
    summary = run(
        db_path=args.db,
        taxonomy_path=args.taxonomy,
        mode=("failed" if args.only_failed else ("all" if args.reset else "todo")),
        limit=args.limit,
    )
    print(
        "\n汇总: 总数 {total} | 成功 {done} | 失败 {failed} | "
        "产卡 {cards} | 待复核 {review} | 空数组 {empty}".format(**summary)
    )


def _cmd_review(args):
    from .review import export_review
    out = export_review(
        db_path=args.db, out_path=args.out,
        concept=args.concept, target=args.target, polarity=args.polarity,
        needs_review=not args.all,
    )
    print(f"\n已导出: {out}")


def _cmd_stats(args):
    from .store import ExtractStore
    with ExtractStore(args.db) as store:
        con = store.con()
        total = con.execute("SELECT count(*) FROM posts").fetchone()[0]
        by_status = con.execute(
            "SELECT status, count(*) FROM extract_status GROUP BY status"
        ).fetchall()
        n_cards = con.execute("SELECT count(*) FROM cards").fetchone()[0]
        n_review = con.execute("SELECT count(*) FROM cards WHERE needs_review").fetchone()[0]
        top_concepts = con.execute(
            "SELECT c, count(*) n FROM (SELECT unnest(concepts) AS c FROM cards) "
            "GROUP BY c ORDER BY n DESC LIMIT 15"
        ).fetchall()
    print(f"发帖总数: {total}")
    print("处理状态:", dict(by_status) or "（尚未处理）")
    print(f"卡片总数: {n_cards}，待复核: {n_review}")
    print("概念分布:")
    for c, n in top_concepts:
        print(f"  {c}: {n}")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m extract", description="情绪周期发帖结构化抽取管道")
    sub = parser.add_subparsers(dest="command")

    sp_run = sub.add_parser("run", help="批量抽取")
    sp_run.add_argument("--db", default=DEFAULT_DB, help=f"DuckDB 路径（默认 {DEFAULT_DB}）")
    sp_run.add_argument("--taxonomy", default=DEFAULT_TAXONOMY, help="taxonomy.yaml 路径")
    sp_run.add_argument("--limit", type=int, default=None, help="只跑前 N 条（小批校准）")
    sp_run.add_argument("--only-failed", action="store_true", help="只重试失败的帖")
    sp_run.add_argument("--reset", action="store_true", help="全量重抽（含已完成，重跑覆盖）")
    sp_run.set_defaults(func=_cmd_run)

    sp_rev = sub.add_parser("review", help="导出复核队列/查询结果")
    sp_rev.add_argument("--db", default=DEFAULT_DB)
    sp_rev.add_argument("--out", default="./output/review.md", help="输出 Markdown 路径")
    sp_rev.add_argument("--concept", default=None, help="按概念筛选")
    sp_rev.add_argument("--target", default=None, help="按标的筛选")
    sp_rev.add_argument("--polarity", default=None, help="按正反例筛选（正例/反例/中性/不适用）")
    sp_rev.add_argument("--all", action="store_true", help="导出全部（默认仅 needs_review）")
    sp_rev.set_defaults(func=_cmd_review)

    sp_stat = sub.add_parser("stats", help="查看处理进度与概念分布")
    sp_stat.add_argument("--db", default=DEFAULT_DB)
    sp_stat.set_defaults(func=_cmd_stats)

    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        sys.exit(1)
    try:
        args.func(args)
    except (ValueError, FileNotFoundError) as e:
        logger.error(str(e))
        sys.exit(1)
    except duckdb.Error as e:
        logger.error(f"数据库错误: {e}（确认 --db 路径正确，且已用爬虫写入 posts 表）")
        sys.exit(1)


if __name__ == "__main__":
    main()
