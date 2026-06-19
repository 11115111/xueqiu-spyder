# xueqiu-spyder

雪球(Xueqiu)爬虫工具，可爬取个股热门讨论、筛选大V观点并生成 Markdown 报告，也可爬取指定用户的全部帖子或专栏。

## 功能

- **股票大V观点** — 爬取某只股票的热门讨论，按评论数筛选大V，汇总观点生成报告
- **用户帖子爬取** — 爬取指定用户的全部帖子/专栏，支持按时间过滤
- **用户搜索** — 按关键词搜索雪球用户，获取用户ID

## 前置条件

- Python 3.9+
- Chrome 浏览器（用于连接调试端口爬取数据）

> 程序会自动在常见安装位置查找 Chrome（Windows 的用户级与系统级目录、macOS 的 Applications、Linux 的 PATH 与常见路径）。
> 如果 Chrome 安装在非默认位置导致找不到，可通过环境变量 `CHROME_PATH` 指定可执行文件完整路径，例如：
>
> ```powershell
> # Windows PowerShell
> $env:CHROME_PATH="C:\Program Files\Google\Chrome\Application\chrome.exe"
> ```

## 安装

```bash
git clone https://github.com/<your-username>/xueqiu-spyder.git
cd xueqiu-spyder
pip install -r requirements.txt
```

## Cookie 设置

雪球**未登录时只能获取首页/第一页公开数据**，翻页或查看更多会提示「请登录雪球查看更多内容」。
因此爬取用户全部帖子前需配置登录态 Cookie：

```bash
python setup_cookie.py
```

在 Chrome 中打开 https://xueqiu.com 并登录，按 `F12 -> Application -> Cookies -> https://xueqiu.com`，
按提示粘贴 `xq_a_token` 等 Cookie 值，脚本会保存到 `.cookies.json`（已在 .gitignore 中排除，不会被提交）。
爬虫启动时会自动把这些 Cookie 注入浏览器。若 token 过期再次出现登录提示，重新运行本脚本更新即可。

## 使用

### 股票大V观点

```bash
python main.py stock <股票代码> [--min-reply 20] [--max-pages 20] [--output ./output]
```

### 用户帖子爬取

```bash
python main.py user <用户ID或用户名> [--max-pages 10] [--all] [--days 30] [--full-text] [--db ./xueqiu.duckdb] [--no-db]
```

> 用户帖子**直接写入 DuckDB，不再生成 Markdown 文件**。需要任何视图/过滤都用 SQL 查询数据库即可。

- `--all` 爬取该用户**全部**帖子，翻到没有更多为止（忽略 `--max-pages`，受 `config.MAX_USER_PAGES` 上限保护）
- `--days N` 只爬最近 N 天，命中时间下限即提前停止翻页，减少请求
- `--full-text` 补全被截断的长文全文（会额外访问详情页，请求量更大）
- `--db PATH` 指定 DuckDB 数据库文件路径（默认 `./xueqiu.duckdb`）
- `--no-db` 本次不写入数据库（仅爬取，不落库）
- 支持直接传用户名，会自动搜索解析为数字ID

> **反封禁说明**：爬取用户全部帖子时内置了节流策略——每次请求带随机抖动间隔、
> 每翻若干页做一次较长休息、检测到限流/风控（HTTP 429/403 或非 JSON 响应）时自动指数退避重试。
> 相关参数可在 `config.py` 中调整：`REQUEST_DELAY`、`REQUEST_DELAY_JITTER`、
> `LONG_REST_EVERY`、`LONG_REST_SECONDS`、`RATE_LIMIT_BACKOFF` 等。
> 如需更稳妥（爬取量大、账号重要），建议调大 `REQUEST_DELAY` 与 `LONG_REST_SECONDS`。

### 搜索用户

```bash
python main.py search <关键词>
```

## 数据存储（DuckDB）

用户帖子的抓取结果会写入 DuckDB（用户命令唯一的输出），便于后续做 SQL 分析或增量积累历史数据：

- 默认数据库文件：`./xueqiu.duckdb`（已在 `.gitignore` 中排除）
- 表 `posts`：以 `post_id` 为主键**幂等去重**，重复爬取只会更新不会重复插入；含清洗后的纯文本 `text`、原始 HTML `description`、是否专栏 `is_column`、互动数据（评论/点赞/转发/收藏/浏览）、`raw_json` 完整原始字段等
- 表 `users`：记录用户名、帖子数、最近抓取时间

### 去重

写入采用主键 + `INSERT OR REPLACE`，**反复爬取同一用户不会产生重复数据**，已存在的帖子会用最新数据覆盖（点赞/评论数等随之更新）。

如果是早期遗留、或从其它来源导入、可能含重复的历史库，可手动清理一次（按 `post_id` 保留最近抓取的一条，可安全反复执行）：

```bash
python main.py dedup [--db ./xueqiu.duckdb]
```

需要按时间、专栏等维度筛选时，直接用 SQL 查询，例如：

```bash
python -c "import duckdb; print(duckdb.connect('xueqiu.duckdb').sql('SELECT screen_name, count(*) FROM posts GROUP BY 1'))"
```

```sql
-- 某用户点赞最高的 10 条帖子
SELECT created_at, like_count, reply_count, text
FROM posts WHERE user_id = 9548638136
ORDER BY like_count DESC LIMIT 10;

-- 某用户最近 30 天的专栏文章
SELECT created_at, title, text FROM posts
WHERE user_id = 9548638136 AND is_column
  AND created_at >= now() - INTERVAL 30 DAY
ORDER BY created_at DESC;
```

## 示例

```bash
# 爬取大族激光的大V观点
python main.py stock SZ002738 --min-reply 20 --max-pages 10

# 爬取用户"治雨"的全部帖子并存入 DuckDB（含长文全文）
python main.py user 治雨 --all --full-text

# 爬取用户最近30天的帖子
python main.py user 9548638136 --days 30

# 搜索用户
python main.py search 治雨
```

## 作为 Claude Code Skill 使用

本项目也是一个 [Claude Code Skill](https://docs.anthropic.com/en/docs/claude-code)。将本仓库克隆到 `~/.claude/skills/` 目录下即可在 Claude Code 中直接调用：

```
~/.claude/skills/xueqiu-spyder/
```

## 输出

在 `./output/` 目录下生成 Markdown 格式的报告。

## 免责声明

本工具仅供学习和研究使用。请遵守雪球的使用条款，合理控制爬取频率。
