---
name: xueqiu-spyder
description: 爬取雪球(Xueqiu)个股热门讨论，通过评论数筛选大V，汇总其对该股票的观点并生成报告。也可爬取指定大V用户的全部帖子并存入 DuckDB。当用户需要查看某只股票的大V观点、市场情绪分析、或某位大V的发帖记录时使用。
---

# 雪球爬虫工具

## 使用场景
- 用户想了解某只股票在雪球上的大V观点
- 用户提供股票代码（如 SH600519、SZ002738）
- 用户想做个股舆情/情绪分析
- 用户想爬取某位特定大V的帖子记录

## 使用方式

### 1. 股票大V观点

```bash
python main.py stock <股票代码> [--min-reply 20] [--max-pages 20] [--output ./output]
```

### 2. 用户帖子爬取

```bash
python main.py user <用户ID或用户名> [--max-pages 10] [--all] [--days 30] [--full-text] [--db ./xueqiu.duckdb] [--no-db]
```

支持直接传用户名（如 `治雨`），会自动搜索并解析为数字ID。也可传数字ID。
用户帖子**直接写入 DuckDB，不再生成 Markdown 文件**；需要筛选时用 SQL 查询 `posts` 表。

### 3. 搜索用户

```bash
python main.py search <关键词>
```

## 示例

```bash
python main.py stock SZ002738 --min-reply 20 --max-pages 10
python main.py user 治雨 --all --full-text
python main.py user 9548638136 --days 30
python main.py search 治雨
```

## 输出
- 股票大V观点：在 `./output/` 目录下生成 Markdown 报告。
- 用户帖子：写入 DuckDB（默认 `./xueqiu.duckdb`），表 `posts`/`users`，按 `post_id` 幂等去重。
