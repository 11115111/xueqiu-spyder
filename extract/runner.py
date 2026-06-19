"""批量编排：并发调用 LLM、串行写库、断点续跑、进度与汇总。

并发只发生在 LLM 调用（IO 密集）；DuckDB 读写都在主线程，保证单线程安全。
重试/退避在 LLMClient 内完成；解析失败/最终失败 → failed 表 + mark failed。
"""
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from .config import LLMConfig, Taxonomy
from .llm_client import LLMClient
from .prompt import build_system_prompt
from .extractor import extract_post
from .store import ExtractStore

logger = logging.getLogger(__name__)


def _extract_one(post, llm, system_prompt, taxonomy):
    t0 = time.time()
    cards = extract_post(post, llm, system_prompt, taxonomy)
    return cards, time.time() - t0


def run(db_path, taxonomy_path=None, mode="todo", limit=None, llm=None, cfg=None,
        llm_config_path=None):
    """运行抽取管道。返回汇总 dict。

    mode: 'todo'(默认，未完成) | 'failed'(仅重试失败) | 'all'(全量重抽)
    limit: 小批校准用，只跑前 N 条
    llm:   可注入自定义客户端（测试用）；默认按配置构建
    cfg:   可直接注入 LLMConfig；默认从 llm.yaml + 环境变量加载
    """
    cfg = cfg or LLMConfig.load(llm_config_path)
    taxonomy = Taxonomy.load(taxonomy_path)
    system_prompt = build_system_prompt(taxonomy)
    llm = llm or LLMClient(cfg)

    summary = {"total": 0, "done": 0, "failed": 0, "cards": 0, "review": 0, "empty": 0}
    store = ExtractStore(db_path)
    try:
        posts = list(store.iter_posts(mode=mode, limit=limit))
        summary["total"] = len(posts)
        if not posts:
            logger.info("没有待处理的帖子")
            return summary
        logger.info(
            f"待处理 {len(posts)} 条，并发 {cfg.concurrency}，"
            f"rpm {cfg.rpm if cfg.rpm else '不限'}，"
            f"prompt_cache {cfg.prompt_cache}，模型 {cfg.model}"
        )

        with ThreadPoolExecutor(max_workers=max(1, cfg.concurrency)) as ex:
            futures = {
                ex.submit(_extract_one, p, llm, system_prompt, taxonomy): p
                for p in posts
            }
            processed = 0
            for fut in as_completed(futures):
                post = futures[fut]
                pid = post["post_id"]
                processed += 1
                try:
                    cards, elapsed = fut.result()
                except Exception as e:
                    raw = getattr(e, "raw", None)
                    store.log_failed(pid, e, raw)
                    store.mark_status(pid, "failed")
                    summary["failed"] += 1
                    logger.warning(f"[{processed}/{len(posts)}] {pid} 失败: {e}")
                    continue

                n = store.upsert_cards(
                    pid, cards, model=cfg.model, source_post_date=post.get("post_date")
                )
                store.mark_status(pid, "done", n)
                summary["done"] += 1
                summary["cards"] += n
                review = sum(1 for c in cards if c.get("needs_review"))
                summary["review"] += review
                if n == 0:
                    summary["empty"] += 1
                logger.info(
                    f"[{processed}/{len(posts)}] {pid} -> {n} 卡"
                    f"（复核 {review}），{elapsed:.1f}s"
                )
    finally:
        store.close()

    logger.info(
        "汇总: 总数 %(total)d | 成功 %(done)d | 失败 %(failed)d | "
        "产卡 %(cards)d | 待复核 %(review)d | 空数组 %(empty)d" % summary
    )
    stats = getattr(llm, "stats", None)
    if stats and stats.get("prompt_tokens"):
        pt, ct = stats["prompt_tokens"], stats["cached_tokens"]
        rate = (ct / pt * 100) if pt else 0
        summary["prompt_tokens"] = pt
        summary["cached_tokens"] = ct
        logger.info(
            f"Token: prompt {pt} | 缓存命中 {ct}（{rate:.0f}%）| "
            f"completion {stats['completion_tokens']}"
        )
        if ct == 0 and stats.get("calls", 0) >= 2:
            logger.warning(
                "缓存命中为 0。排查方向："
                "①看上方 LLM usage 日志里是否存在缓存字段（无 → 该端点未透出/未启用缓存，"
                "常见于聚合代理）；②Gemini 隐式缓存仅 2.5+ 且需公共前缀超阈值（Flash-Lite≈2048 token，"
                "本管道 system≈2.4k+ 通常达标）；③首条必为 miss，需连续多条才回填命中。"
            )
    return summary
